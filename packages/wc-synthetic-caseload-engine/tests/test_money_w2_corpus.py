"""Money W2 showcase semantic, provenance, and determinism oracles."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml

from conftest import extract_text
from wc_caseload_engine.manifests import generate_case
from wc_caseload_engine.planner import build_case_plan
from wc_caseload_engine.renderer import (
    DEFENSE_LENS_RNG_STREAMS,
    RATING_RNG_STREAMS,
    doctrine_flowables,
)
from wc_caseload_engine.seeds import load_caseload_spec, resolve_caseload
from wc_caseload_engine.substrate import find_substrate

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from golden_gate import CI_TIER, CORPORA, digest_corpus

PACKAGE = Path(__file__).resolve().parents[1]
W2_SPEC = PACKAGE / "examples" / "money-w2-showcase.yaml"

EXPECTED_CASES = (
    ("w2-rating-anchor", 62001),
    ("w2-rating-dfec", 62002),
    ("w2-rating-paired", 62003),
    ("w2-rating-election", 62004),
    ("w2-rating-ceiling", 62005),
    ("w2-file-review", 61001),
    ("w2-reserve-development", 61000),
    ("w2-reserve-sequence", 61002),
    ("w2-reserve-reassessment", 61005),
    ("w2-reserve-neighbor", 61009),
    ("w2-joint-evaluation", 61012),
    ("w2-assertion-channel", 62012),
)
FORBIDDEN_DILIGENCE_WORDS = ("attentive", "ordinary", "negligent")
EXPECTED_RATING_STREAMS = ("rating:doctrine",)
EXPECTED_DEFENSE_STREAMS: tuple[str, ...] = ()


def _raw_spec() -> dict[str, Any]:
    value = yaml.safe_load(W2_SPEC.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _raw_diligence_paths(value: dict[str, Any]) -> tuple[str, ...]:
    found: list[str] = []
    for index, case in enumerate(value.get("cases", ())):
        scenario = case.get("scenario") or {}
        adjuster = scenario.get("adjuster") or {}
        if "diligence" in adjuster:
            found.append(f"cases[{index}].scenario.adjuster.diligence")
    return tuple(found)


@pytest.fixture(scope="module")
def w2_plans() -> dict[str, Any]:
    if find_substrate() is None:
        pytest.skip("merus-test-data-generator substrate not on disk")
    spec = load_caseload_spec(W2_SPEC)
    return {
        seed.case_id: build_case_plan(seed, case_number=index)
        for index, seed in enumerate(resolve_caseload(spec), 1)
    }


def _generate_cli(spec: Path, out: Path, *, zone: str, hash_seed: str) -> None:
    environment = dict(os.environ)
    environment.update(
        {
            "TZ": zone,
            "PYTHONHASHSEED": hash_seed,
            "OMP_THREAD_LIMIT": "1",
        }
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "wc_caseload_engine",
            "generate",
            "--spec",
            str(spec),
            "--out",
            str(out),
        ],
        cwd=PACKAGE,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout[-4000:] + completed.stderr[-4000:]


@pytest.fixture(scope="module")
def w2_generated_outputs(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    if find_substrate() is None:
        pytest.skip("merus-test-data-generator substrate not on disk")
    root = tmp_path_factory.mktemp("money-w2-process-tz")
    west = root / "west"
    east = root / "east"
    _generate_cli(
        W2_SPEC,
        west,
        zone="America/Los_Angeles",
        hash_seed="0",
    )
    _generate_cli(
        W2_SPEC,
        east,
        zone="Australia/Sydney",
        hash_seed="424242",
    )
    return west, east


def _defense_events(defense: Any) -> tuple[Any, ...]:
    return (defense.initial_file_review, *defense.reserve_events)


def _bucket_tuple(amounts: Any) -> tuple[Decimal, Decimal, Decimal]:
    return (amounts.indemnity, amounts.medical, amounts.expense_alae)


def _kite_scan_problems(
    raw: dict[str, Any], emitted_methods: dict[str, str | None]
) -> tuple[str, ...]:
    problems: list[str] = []
    for case in raw["cases"]:
        case_id = case["case_id"]
        rating = (case.get("scenario") or {}).get("rating")
        if rating is None:
            continue
        raw_opt_in = rating.get("kite_addition") is not None
        emitted = emitted_methods.get(case_id)
        if raw_opt_in != (emitted == "kite_addition"):
            problems.append(
                f"{case_id}: raw_opt_in={raw_opt_in}, emitted_method={emitted!r}"
            )
    return tuple(problems)


def _stream_registry_problems(
    declared: set[str], exercised: set[str]
) -> tuple[str, ...]:
    return tuple(
        [f"declared but unexercised: {name}" for name in sorted(declared - exercised)]
        + [f"exercised but undeclared: {name}" for name in sorted(exercised - declared)]
    )


def test_w2_raw_yaml_omits_adjuster_diligence_and_uses_neutral_names() -> None:
    """m23-47/R100/R102: corpus policy is derived, never authored or leaked by name."""
    raw = _raw_spec()
    assert tuple((case["case_id"], case["rng_seed"]) for case in raw["cases"]) == (
        EXPECTED_CASES
    )
    assert _raw_diligence_paths(raw) == ()
    assert all(
        word not in case_id.lower()
        for case_id, _seed in EXPECTED_CASES
        for word in FORBIDDEN_DILIGENCE_WORDS
    )
    assert raw["defaults"]["output"]["filename_style"] == "neutral"

    planted = copy.deepcopy(raw)
    planted["cases"][0]["scenario"]["adjuster"] = {"diligence": "negligent"}
    assert _raw_diligence_paths(planted) == (
        "cases[0].scenario.adjuster.diligence",
    )


def test_w2_corpus_has_one_exact_ci_registry_row_and_golden() -> None:
    """R100: the new source and sole recording are registered at CI tier."""
    rows = [corpus for corpus in CORPORA if corpus.name == "money-w2-showcase"]
    assert len(rows) == 1
    row = rows[0]
    assert row.tier == CI_TIER
    assert row.spec == W2_SPEC
    assert row.golden == PACKAGE / "tests" / "golden" / "money-w2-showcase.json"
    golden = json.loads(row.golden.read_text(encoding="utf-8"))
    assert golden["caseCount"] == 12
    assert golden["documentCount"] == 576
    assert golden["fileCount"] == 626
    assert set(golden["cases"]) == {case_id for case_id, _seed in EXPECTED_CASES}


def test_w2_rating_and_defense_semantics_are_literal(w2_plans: dict[str, Any]) -> None:
    """R100: every required branch has independent, hand-stated outcomes."""
    anchor = w2_plans["w2-rating-anchor"].case_facts.rating
    assert anchor is not None
    assert anchor.applicant_age == 30
    assert anchor.final_pd_percent == 11
    assert anchor.rating_string == "15.01.02.02 - 8 - [5]10 - 470H - 13 - 11%"

    dfec = w2_plans["w2-rating-dfec"].case_facts.rating
    assert dfec is not None
    row = dfec.impairments[0]
    assert (
        row.adjustment_method,
        row.fec_rank,
        row.adjustment_factor,
        row.schedule_adjusted,
        row.occupation_adjusted,
        row.age_adjusted,
    ) == ("dfec_1_4", None, Decimal("1.4"), 11, 14, 12)
    assert row.rating_string == "15.01.02.02 - 8 - [1.4]11 - 470H - 14 - 12%"

    scheduled = w2_plans["w2-rating-paired"].case_facts.rating
    elected = w2_plans["w2-rating-election"].case_facts.rating
    capped = w2_plans["w2-rating-ceiling"].case_facts.rating
    assert scheduled is not None and elected is not None and capped is not None
    assert (
        scheduled.combination_method,
        scheduled.scheduled_combined_rating,
        scheduled.combined_rating,
        scheduled.kite_impairment_ids,
    ) == ("cvc", 26, 26, None)
    assert "Kite addition" not in scheduled.rating_string
    assert (
        elected.combination_method,
        elected.kite_impairment_ids,
        elected.scheduled_combined_rating,
        elected.combined_rating,
    ) == ("kite_addition", ("shoulder", "knee"), 26, 28)
    assert (
        capped.scheduled_combined_rating,
        capped.combined_rating,
        capped.final_pd_percent,
    ) == (78, 100, 100)

    review = w2_plans["w2-file-review"].money_facts.defense
    material = w2_plans["w2-reserve-development"].money_facts.defense
    sequence = w2_plans["w2-reserve-sequence"].money_facts.defense
    decrease = w2_plans["w2-reserve-reassessment"].money_facts.defense
    neighbor = w2_plans["w2-reserve-neighbor"].money_facts.defense
    assert all(item is not None for item in (review, material, sequence, decrease, neighbor))

    review_events = _defense_events(review)
    assert len(review_events) == 1
    assert _bucket_tuple(review_events[0].booked_snapshot.outstanding_reserve) == (
        Decimal("24000.00"),
        Decimal("36000.00"),
        Decimal("10000.00"),
    )
    assert review.scorer_labels.reserve_adequacy == "adequate"

    material_events = _defense_events(material)
    assert tuple(event.booked_snapshot.outstanding_reserve.total for event in material_events) == (
        Decimal("60000.00"),
        Decimal("120000.00"),
    )
    assert sequence.scorer_labels.stair_stepping is True
    assert sequence.scorer_labels.reserve_adequacy == "under_reserved"
    assert tuple(
        event.booked_snapshot.outstanding_reserve.total
        for event in _defense_events(sequence)
    ) == (
        Decimal("40000.00"),
        Decimal("60000.00"),
        Decimal("80000.00"),
        Decimal("100000.00"),
    )

    decrease_events = _defense_events(decrease)
    assert tuple(event.recommendation.outstanding_reserve.total for event in decrease_events) == (
        Decimal("100000.00"),
        Decimal("120000.00"),
        Decimal("115000.00"),
    )
    assert tuple(event.booked_snapshot.outstanding_reserve.total for event in decrease_events) == (
        Decimal("75000.00"),
        Decimal("120000.00"),
        Decimal("120000.00"),
    )
    assert _bucket_tuple(decrease_events[-1].recommendation.outstanding_reserve) == (
        Decimal("46000.00"),
        Decimal("57500.00"),
        Decimal("11500.00"),
    )
    assert _bucket_tuple(decrease_events[-1].booked_snapshot.outstanding_reserve) == (
        Decimal("48000.00"),
        Decimal("60000.00"),
        Decimal("12000.00"),
    )
    assert decrease.scorer_labels.reserve_adequacy == "over_reserved"

    neighbor_events = _defense_events(neighbor)
    assert tuple(
        (
            event.exposure.trigger,
            event.exposure.low,
            event.exposure.expected,
            event.exposure.high,
        )
        for event in neighbor_events
    ) == tuple(
        (
            event.exposure.trigger,
            event.exposure.low,
            event.exposure.expected,
            event.exposure.high,
        )
        for event in decrease_events
    )
    assert neighbor_events[-1].booked_snapshot.outstanding_reserve.total == Decimal(
        "115000.00"
    )
    assert neighbor.scorer_labels.reserve_adequacy == "adequate"

    joint = w2_plans["w2-joint-evaluation"]
    assert joint.case_facts.rating is not None
    assert joint.money_facts.defense is not None
    assert not joint.warnings


def test_w2_raw_kite_opt_in_is_bijective_with_emitted_method(
    w2_plans: dict[str, Any],
) -> None:
    """R42/R100 Form C: raw non-null pair and emitted addition are iff."""
    methods = {
        case_id: (
            None
            if plan.case_facts.rating is None
            else plan.case_facts.rating.combination_method
        )
        for case_id, plan in w2_plans.items()
    }
    raw = _raw_spec()
    assert _kite_scan_problems(raw, methods) == ()

    planted = dict(methods)
    planted["w2-rating-paired"] = "kite_addition"
    assert _kite_scan_problems(raw, planted) == (
        "w2-rating-paired: raw_opt_in=False, emitted_method='kite_addition'",
    )


def test_w2_semantic_rng_registries_are_exact_and_identity_keyed(
    w2_plans: dict[str, Any],
) -> None:
    """R101: exact registries, exercised families, and index-inert rating prose."""
    assert RATING_RNG_STREAMS == EXPECTED_RATING_STREAMS
    assert DEFENSE_LENS_RNG_STREAMS == EXPECTED_DEFENSE_STREAMS
    declared = set(EXPECTED_RATING_STREAMS) | set(EXPECTED_DEFENSE_STREAMS)
    assert all(
        stream.startswith("rating:") or stream.startswith("defense-lens:")
        for stream in declared
    )

    exercised = {
        "rating:doctrine"
        for plan in w2_plans.values()
        if plan.case_facts.rating is not None
        and any(
            document.content_flags
            and (document.semantic_event_id or "").startswith("rating:")
            for document in plan.documents
        )
    }
    assert _stream_registry_problems(declared, exercised) == ()
    assert _stream_registry_problems(
        declared | {"rating:declared-but-unexercised"}, exercised
    ) == ("declared but unexercised: rating:declared-but-unexercised",)
    assert _stream_registry_problems(declared, set()) == (
        "declared but unexercised: rating:doctrine",
    )

    for relative in ("rating.py", "defense_lens.py"):
        source = (PACKAGE / "src" / "wc_caseload_engine" / relative).read_text(
            encoding="utf-8"
        )
        assert "derive_seed(" not in source
        assert "seed.rng(" not in source
        assert "random.Random(" not in source

    plan = w2_plans["w2-rating-paired"]
    document = next(
        item
        for item in plan.documents
        if item.subtype == "PD_RATING_CONVERSION" and "kite" in item.content_flags
    )
    assert document.semantic_event_id == "rating:carrier:PD_RATING_CONVERSION"

    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import HRFlowable

    styles = getSampleStyleSheet()
    for name in ("BodyText14", "SmallItalic", "SectionHeader"):
        styles.add(ParagraphStyle(name=name, parent=styles["BodyText"]))

    class Template:
        def __init__(self) -> None:
            self.styles = styles
            self._wc_case_facts = plan.case_facts

        @staticmethod
        def make_hr() -> HRFlowable:
            return HRFlowable()

    def selected_text(index: int) -> tuple[str, ...]:
        return tuple(
            item.getPlainText()
            for item in doctrine_flowables(
                Template(),
                subtype=document.subtype,
                seed=plan.seed,
                index=index,
                content_flags=document.content_flags,
                semantic_event_id=document.semantic_event_id,
            )
            if hasattr(item, "getPlainText")
        )

    assert selected_text(2) == selected_text(2002)


def test_w2_is_byte_identical_across_processes_hash_salts_and_timezones(
    w2_generated_outputs: tuple[Path, Path],
) -> None:
    """R100/R101: two fresh CLI generations cover repeat, hash, and TZ controls."""
    west, east = w2_generated_outputs
    assert digest_corpus(west) == digest_corpus(east)


def test_w2_generated_public_and_truth_outputs_pin_reserve_behavior(
    w2_generated_outputs: tuple[Path, Path],
) -> None:
    """R100: analyzer-visible buckets and scorer-only policy outcomes agree."""
    west, _east = w2_generated_outputs
    public = yaml.safe_load(
        (west / "w2-reserve-reassessment" / "case_facts.yaml").read_text(
            encoding="utf-8"
        )
    )["money"]["defense"]
    assert "scorerLabels" not in public
    assert tuple(
        event["expected"]["total"] for event in public["exposureEvents"]
    ) == ("100000.00", "120000.00", "115000.00")
    assert public["exposureEvents"][-1]["expected"] == {
        "indemnity": "46000.00",
        "medical": "57500.00",
        "expenseAlae": "11500.00",
        "total": "115000.00",
    }
    assert len(public["reserveEvents"]) == 2
    assert "artifactBinding" not in public["reserveEvents"][-1]
    assert public["reserveEvents"][-1]["bookedSnapshot"]["outstandingReserve"] == {
        "indemnity": "48000.00",
        "medical": "60000.00",
        "expenseAlae": "12000.00",
        "total": "120000.00",
    }

    truth = json.loads(
        (west / "truth" / "w2-reserve-reassessment.truth.json").read_text(
            encoding="utf-8"
        )
    )["channels"]["money"]["defense"]
    assert truth["scorerLabels"] == {
        "stairStepping": False,
        "reserveAdequacy": "over_reserved",
    }
    neighbor = json.loads(
        (west / "truth" / "w2-reserve-neighbor.truth.json").read_text(
            encoding="utf-8"
        )
    )["channels"]["money"]["defense"]
    assert neighbor["scorerLabels"] == {
        "stairStepping": False,
        "reserveAdequacy": "adequate",
    }

    manifest = json.loads(
        (west / "w2-reserve-reassessment" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    reserve_files = [
        west / "w2-reserve-reassessment" / "documents" / entry["filename"]
        for entry in manifest["documents"]
        if entry["subtype"] in {"RESERVE_WORKSHEET", "RESERVE_CHANGE_NOTICE"}
    ]
    paper = "\n".join(extract_text(path, "pdf") for path in reserve_files)
    assert all(label in paper for label in ("Indemnity", "Medical", "Expense / ALAE"))
    assert all(
        amount in paper
        for amount in ("$40,000.00", "$50,000.00", "$10,000.00", "$120,000.00")
    )


def test_w2_assertion_case_generates_default_v1_and_explicit_v2(
    tmp_path: Path,
    w2_plans: dict[str, Any],
) -> None:
    """R100: one corpus seed exercises default v1 and separate explicit v2 writers."""
    plan = w2_plans["w2-assertion-channel"]
    default_root = tmp_path / "default"
    explicit_root = tmp_path / "explicit"
    default = generate_case(
        plan.seed,
        default_root,
        truth_dir=default_root / "truth",
    )
    explicit = generate_case(
        plan.seed,
        explicit_root,
        truth_dir=explicit_root / "truth",
        truth_manifest_version=2,
    )
    default_channel = json.loads(default.truth_path.read_text(encoding="utf-8"))[
        "channels"
    ]["assertions"]
    explicit_channel = json.loads(explicit.truth_path.read_text(encoding="utf-8"))[
        "channels"
    ]["assertions"]
    assert default_channel["channelVersion"] == "1.0.0"
    assert explicit_channel["channelVersion"] == "2.0.0"
    assert default_channel != explicit_channel
