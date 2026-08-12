"""Regression tests for timezone- and clock-independent output.

The reproduction: running the demo caseload under ``TZ=Australia/Sydney``
produced 55 of 289 files different from the same command under ``TZ=UTC`` —
every ``.eml`` (a local-offset ``Date:`` header), fifteen PDFs and two DOCX
files (content computed from ``date.today()``, which had already rolled over in
Sydney), and the six manifests that carry their checksums.

Same-machine determinism was real; cross-machine determinism was not, and the
same tree would also have drifted from one day to the next.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import zipfile
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from conftest import requires_substrate
from wc_caseload_engine.determinism import (
    DISABLE_REEXEC_VAR,
    MAX_REEXEC_HOPS,
    REEXEC_GUARD_VAR,
    REEXEC_MODULE,
    SYNTHETIC_EML_HEADER,
    SYNTHETIC_MARKER,
    fixed_utc_datetime,
    hashing_is_stable,
    normalize_eml,
    pdf_date_string,
    pin_substrate_clock,
    zip_date_time,
)
from wc_caseload_engine.manifests import generate_case
from wc_caseload_engine.medical_assertions import (
    MEDICAL_STORY_HASH_SEEDS,
    MEDICAL_STORY_REPEAT_GENERATIONS,
    MEDICAL_STORY_TZ_MATRIX,
    canonical_story_key,
)
from wc_caseload_engine.planner import build_case_plan
from wc_caseload_engine.seeds import (
    ANCHOR_DATE,
    parse_case_seed,
    parse_caseload_spec,
)
from wc_caseload_engine.substrate import import_substrate

# Two zones on opposite sides of the date line, chosen so that for most of the
# UTC day they disagree about what "today" is — which is precisely the bug.
ZONE_EAST = "Australia/Sydney"
ZONE_WEST = "America/Los_Angeles"


@contextmanager
def timezone_set(name: str) -> Iterator[None]:
    """Run the block with ``TZ`` set process-wide, then restore it exactly."""
    previous = os.environ.get("TZ")
    os.environ["TZ"] = name
    time.tzset()
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = previous
        time.tzset()


def small_case(case_id: str) -> dict[str, Any]:
    """A case small enough to render twice in a test, covering all four formats."""
    return {
        "case_id": case_id,
        "rng_seed": 987654,
        "injury": {
            "type": "specific",
            "date_of_injury": "2022-05-17",
            "body_parts": [{"part": "lumbar_spine", "icd10": "M54.5"}],
        },
        "lifecycle": {
            "target_stage": "resolved",
            "claim_response": "accepted",
            "eval_type": "qme",
            "resolution": {"type": "c_and_r"},
        },
        "documents": {"global_cap": 12},
        "output": {"formats": ["pdf", "scanned_pdf", "eml", "docx"]},
    }


def medical_case(case_id: str) -> dict[str, Any]:
    """The same probe, opted into the AJC-60 world-truth layer.

    The medical block belongs on a *separate* probe rather than being added to
    ``small_case``, because ``small_case`` is what the whole module's byte claims are
    measured on — folding a new axis into it would silently re-scope every assertion
    above rather than adding one.

    The layer has two clock-shaped surfaces even though it renders nothing. The
    applicant's age is computed from a date of birth against ``ANCHOR_DATE``, and a
    managed condition's onset is dated backwards from the injury. Both are date
    arithmetic, and date arithmetic is precisely what a zone change perturbs — the
    original defect this module exists for was Faker's ``date_of_birth`` landing on
    1999-08-14 in Los Angeles and 1999-08-15 in Sydney.
    """
    case = small_case(case_id)
    case["profile"] = {"applicant": {"age": 52}}
    case["scenario"] = {
        "medical_history": {
            "conditions": [{"label": "type 2 diabetes mellitus", "key": "diabetes"}],
            "prior_claims": [
                {
                    "body_parts": ["lumbar_spine"],
                    "date_of_injury": "2015-01-05",
                    "resolution_type": "stipulated_award",
                    "award": {
                        "body_parts": ["lumbar_spine"],
                        "pd_percent": 12,
                        "award_date": "2016-02-01",
                    },
                }
            ],
        }
    }
    return case


def digest_tree(root: Path) -> dict[str, str]:
    """Path-keyed SHA-256 of every file under *root*."""
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


_MEDICAL_STORY_RENDER_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "medical_story_render_key_pair.yaml"
)


def _medical_story_seed() -> Any:
    payload = __import__("yaml").safe_load(
        _MEDICAL_STORY_RENDER_FIXTURE.read_text(encoding="utf-8")
    )
    spec = parse_caseload_spec(payload)
    assert [(case.case_id, case.rng_seed) for case in spec.cases] == [
        ("render-key-stability", 620401)
    ]
    return spec.cases[0]


def _medical_story_plan_payload(plan: Any) -> dict[str, Any]:
    """Complete canonical M3 plan projection for R65's digest."""

    def dumped(value: Any) -> Any:
        return value.model_dump(mode="json") if value is not None else None

    documents = []
    for document in plan.documents:
        render_key = document.medical_story_render_key
        assert render_key is not None
        documents.append(
            {
                "index": document.index,
                "subtype": document.subtype,
                "parent_type": document.parent_type,
                "doc_date": document.doc_date.isoformat(),
                "doc_format": document.doc_format,
                "track": document.track,
                "author_role": document.author_role,
                "title": document.title,
                "recipient_role": document.recipient_role,
                "content_flags": list(document.content_flags),
                "medical_opinion_id": document.medical_opinion_id,
                "spoken_contention_ids": list(document.spoken_contention_ids),
                "contention_surface": document.contention_surface,
                "template_subtype": document.template_subtype,
                "target_medical_opinion_id": document.target_medical_opinion_id,
                "contention_actor_party": document.contention_actor_party,
                "defense_contest_theories": list(
                    document.defense_contest_theories
                ),
                "imr_target_denial_date": (
                    document.imr_target_denial_date.isoformat()
                    if document.imr_target_denial_date is not None
                    else None
                ),
                "imr_application_content": dumped(
                    document.imr_application_content
                ),
                "imr_outcome": document.imr_outcome,
                "medical_story_render_key": canonical_story_key(render_key),
            }
        )
    return {
        "medical_history": dumped(plan.medical_history),
        "medical_assertions": dumped(plan.medical_assertions),
        "medical_story": dumped(plan.medical_story),
        "medical_ur_plan": dumped(plan.medical_ur_plan),
        "documents": documents,
        "warnings": list(plan.warnings),
    }


def _medical_story_leakage_findings(root: Path) -> list[str]:
    """Bounded R65 leakage vector; step 11 owns the OCR/full-surface gate."""
    import email
    import email.policy

    import fitz
    import yaml as yaml_module

    from test_medical_assertions import (
        _BARE_TOKEN,
        ASSERTION_LEAKAGE_EXEMPTIONS,
        _leakage_reserved_key_findings,
    )

    findings: list[str] = []

    def note(text: str, where: str) -> None:
        if _BARE_TOKEN.search(text.lower()) and where not in ASSERTION_LEAKAGE_EXEMPTIONS:
            findings.append(f"bare token at {where}")

    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if rel == "truth" or rel.startswith("truth/"):
            continue
        note(rel, f"path:{rel}")
        if not path.is_file():
            continue
        raw = path.read_bytes()
        note(raw.decode("utf-8", errors="ignore"), f"bytes:{rel}")
        if path.name in ("seed.yaml", "case_facts.yaml"):
            findings.extend(
                _leakage_reserved_key_findings(
                    yaml_module.safe_load(raw.decode("utf-8")), rel
                )
            )
        elif path.suffix == ".json":
            findings.extend(
                _leakage_reserved_key_findings(
                    json.loads(raw.decode("utf-8")), rel
                )
            )
        elif path.suffix == ".pdf":
            with fitz.open(stream=raw, filetype="pdf") as document:
                note(
                    "\n".join(page.get_text() for page in document),
                    f"pdf-text:{rel}",
                )
        elif path.suffix == ".docx":
            with zipfile.ZipFile(path) as archive:
                for name in archive.namelist():
                    if name.endswith(".xml"):
                        note(
                            archive.read(name).decode("utf-8", errors="replace"),
                            f"docx:{rel}!{name}",
                        )
        elif path.suffix == ".eml":
            message = email.message_from_bytes(raw, policy=email.policy.default)
            for part in message.walk():
                if part.get_content_maintype() == "text":
                    note(str(part.get_content()), f"eml:{rel}")
    return sorted(findings)


def _medical_story_observation(out: Path) -> dict[str, Any]:
    """One R65 observation across every required plan/output surface."""
    from wc_caseload_engine import medical_assertions as assertion_module
    from wc_caseload_engine.truth_manifest import build_case_truth_manifest

    seed = _medical_story_seed()
    family_counts: Counter[str] = Counter()
    original_seed = assertion_module._medical_story_seed

    def counting_seed(seed_obj: Any, family: str, semantic_key: Any) -> int:
        family_counts[family] += 1
        return original_seed(seed_obj, family, semantic_key)

    assertion_module._medical_story_seed = counting_seed
    try:
        result = generate_case(seed, out, case_number=1)
    finally:
        assertion_module._medical_story_seed = original_seed

    plan_payload = _medical_story_plan_payload(result.plan)
    plan_bytes = json.dumps(
        plan_payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    truth = build_case_truth_manifest(result.plan)
    bindings = [
        {
            "render_key": document["medical_story_render_key"],
            "medical_opinion_id": document["medical_opinion_id"],
            "spoken_contention_ids": document["spoken_contention_ids"],
            "contention_surface": document["contention_surface"],
            "template_subtype": document["template_subtype"],
            "target_medical_opinion_id": document[
                "target_medical_opinion_id"
            ],
            "contention_actor_party": document["contention_actor_party"],
            "defense_contest_theories": document[
                "defense_contest_theories"
            ],
        }
        for document in plan_payload["documents"]
    ]
    dates = [
        (document["medical_story_render_key"], document["doc_date"])
        for document in plan_payload["documents"]
    ]
    return {
        "plan_digest": hashlib.sha256(plan_bytes).hexdigest(),
        "bindings": bindings,
        "dates": dates,
        "truth_assertion_channel": truth["channels"].get("assertions"),
        "output_tree_bytes": digest_tree(result.directory),
        "leakage_findings": _medical_story_leakage_findings(result.directory),
        "story_trace_counters": dict(sorted(family_counts.items())),
    }


def _write_medical_story_observation(out: str, destination: str) -> None:
    observation = _medical_story_observation(Path(out))
    Path(destination).write_text(
        json.dumps(observation, ensure_ascii=True, sort_keys=True),
        encoding="utf-8",
    )


def _medical_story_observation_in_subprocess(
    root: Path,
    hash_seed: str,
) -> dict[str, Any]:
    result_path = root / "observation.json"
    package_root = Path(__file__).resolve().parents[1]
    script = (
        "import sys; "
        "sys.path.insert(0, sys.argv[1]); "
        "from test_timezone_determinism import "
        "_write_medical_story_observation; "
        "_write_medical_story_observation(sys.argv[2], sys.argv[3])"
    )
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = hash_seed
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(Path(__file__).resolve().parent),
            str(root / "out"),
            str(result_path),
        ],
        cwd=package_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-4000:]
    return json.loads(result_path.read_text(encoding="utf-8"))


def _assert_medical_story_observations_equal(
    observations: dict[str, dict[str, Any]],
) -> None:
    """Compare every R65 surface explicitly, with the changed label named."""
    assert len(observations) == 2
    (first_label, first), (second_label, second) = observations.items()
    for field in (
        "plan_digest",
        "bindings",
        "dates",
        "truth_assertion_channel",
        "output_tree_bytes",
        "leakage_findings",
        "story_trace_counters",
    ):
        assert first[field] == second[field], (
            f"medical-story {field} drifted between {first_label} and "
            f"{second_label}"
        )


# ---------------------------------------------------------------------------
# The reproduction
# ---------------------------------------------------------------------------


@requires_substrate
def test_output_is_byte_identical_across_timezones(tmp_path: Path) -> None:
    """The headline guarantee: same seed, different zone, same bytes."""
    seed = parse_case_seed(small_case("tz-probe"))

    with timezone_set(ZONE_WEST):
        west = generate_case(seed, tmp_path / "west", case_number=1).directory
    with timezone_set(ZONE_EAST):
        east = generate_case(seed, tmp_path / "east", case_number=1).directory

    west_digests = digest_tree(west)
    east_digests = digest_tree(east)

    assert set(west_digests) == set(east_digests), "the two runs wrote different files"
    drifted = sorted(name for name in west_digests if west_digests[name] != east_digests[name])
    assert not drifted, (
        f"{len(drifted)} file(s) drifted between {ZONE_WEST} and {ZONE_EAST}: {drifted}"
    )


@requires_substrate
def test_the_medical_history_layer_is_byte_identical_across_timezones(
    tmp_path: Path,
) -> None:
    """AJC-60. The same guarantee, with the world-truth layer opted in.

    The layer publishes nothing, so a drift in it could not show up in the rendered
    tree — which is exactly why the ledger itself is compared as well as the files.
    A derived age or an onset date that moved with the zone would otherwise wait
    until M3 rendered it to become visible, and by then the cause would be a
    milestone away from the symptom.
    """
    seed = parse_case_seed(medical_case("tz-medical"))

    with timezone_set(ZONE_WEST):
        west = generate_case(seed, tmp_path / "west", case_number=1).directory
        west_ledger = build_case_plan(seed).medical_history
    with timezone_set(ZONE_EAST):
        east = generate_case(seed, tmp_path / "east", case_number=1).directory
        east_ledger = build_case_plan(seed).medical_history

    assert west_ledger is not None and east_ledger is not None
    assert west_ledger == east_ledger, (
        "the world-truth ledger differs between "
        f"{ZONE_WEST} and {ZONE_EAST}: {west_ledger.demographics} vs "
        f"{east_ledger.demographics}"
    )
    assert west_ledger.demographics.age == 52 or west_ledger.demographics.age == 51

    west_digests, east_digests = digest_tree(west), digest_tree(east)
    drifted = sorted(name for name in west_digests if west_digests[name] != east_digests[name])
    assert not drifted, f"{len(drifted)} file(s) drifted with the medical layer on: {drifted}"


ALL_FORMATS: frozenset[str] = frozenset({"pdf", "scanned_pdf", "eml", "docx"})
"""Every format the engine emits — each has its own timezone-sensitive surface.

``eml`` carries a Date header, ``docx`` a ZIP entry time and a core-properties
date, ``pdf`` a creation date, ``scanned_pdf`` all of the above plus a rewrite.
A drift probe that exercised three of the four would report a guarantee it had
not tested.
"""


@requires_substrate
def test_every_format_is_actually_exercised_by_the_probe(tmp_path: Path) -> None:
    """A TZ test that renders only PDFs would have passed before the fix.

    Previously asserted ``"eml" in formats`` alone, which is true of any case
    that happens to draw one eml — it said nothing about the other three, and
    nothing at all about the two runs the byte-identity test actually compares.
    """
    west_result = None
    east_result = None
    with timezone_set(ZONE_WEST):
        west_result = generate_case(parse_case_seed(small_case("tz-formats")), tmp_path / "west")
    with timezone_set(ZONE_EAST):
        east_result = generate_case(parse_case_seed(small_case("tz-formats")), tmp_path / "east")

    per_run = {
        ZONE_WEST: {entry["format"] for entry in west_result.manifest["documents"]},  # type: ignore[union-attr]
        ZONE_EAST: {entry["format"] for entry in east_result.manifest["documents"]},  # type: ignore[union-attr]
    }
    for zone, formats in per_run.items():
        assert formats == ALL_FORMATS, (
            f"the {zone} run rendered {sorted(formats)}; the drift comparison only covers "
            f"what it renders, so {sorted(ALL_FORMATS - formats)} would go untested"
        )


# ---------------------------------------------------------------------------
# The substrate clock
# ---------------------------------------------------------------------------


@requires_substrate
class TestSubstrateClockPin:
    """Every substrate reading of "today" resolves to the anchor."""

    def test_the_pin_is_applied_and_idempotent(self) -> None:
        pin_substrate_clock()
        assert pin_substrate_clock() is False

    @pytest.mark.parametrize(
        ("module_name", "attribute"),
        [
            ("data.fake_data_generator", "date"),
            ("pdf_templates.medical.qme_ame_report", "_date"),
            ("pdf_templates.summaries.settlement_memo", "date"),
        ],
    )
    def test_module_level_today_is_the_anchor(self, module_name: str, attribute: str) -> None:
        pin_substrate_clock()
        pinned = getattr(import_substrate(module_name), attribute)
        assert pinned.today() == ANCHOR_DATE

    def test_the_function_local_helper_is_the_anchor(self) -> None:
        """``deposition_exchanges._today`` imports ``date`` inside its body."""
        pin_substrate_clock()
        module = import_substrate("data.deposition_exchanges")
        assert module._today() == ANCHOR_DATE

    def test_the_anchor_is_the_same_in_both_zones(self) -> None:
        pin_substrate_clock()
        module = import_substrate("data.fake_data_generator")
        with timezone_set(ZONE_EAST):
            east = module.date.today()
        with timezone_set(ZONE_WEST):
            west = module.date.today()
        assert east == west == ANCHOR_DATE


# ---------------------------------------------------------------------------
# Timestamp derivations
# ---------------------------------------------------------------------------


class TestTimestampDerivations:
    """Each derivation is pinned to UTC, so none of them move with ``TZ``."""

    SAMPLE = date(2024, 3, 15)

    def test_fixed_utc_datetime_carries_utc_and_ignores_the_zone(self) -> None:
        with timezone_set(ZONE_EAST):
            east = fixed_utc_datetime(self.SAMPLE)
        with timezone_set(ZONE_WEST):
            west = fixed_utc_datetime(self.SAMPLE)
        assert east == west
        assert east.utcoffset().total_seconds() == 0  # type: ignore[union-attr]

    def test_pdf_date_string_states_its_offset_literally(self) -> None:
        with timezone_set(ZONE_EAST):
            east = pdf_date_string(self.SAMPLE)
        with timezone_set(ZONE_WEST):
            west = pdf_date_string(self.SAMPLE)
        assert east == west == "D:20240315120000+00'00'"

    def test_zip_date_time_reads_the_date_fields_not_the_clock(self) -> None:
        with timezone_set(ZONE_EAST):
            east = zip_date_time(self.SAMPLE)
        with timezone_set(ZONE_WEST):
            west = zip_date_time(self.SAMPLE)
        assert east == west
        assert east[:3] == (2024, 3, 15)

    def test_pre_1980_dates_fall_back_to_the_zip_epoch(self) -> None:
        assert zip_date_time(date(1975, 6, 1)) == (1980, 1, 1, 0, 0, 0)


class TestEmlNormalization:
    """The ``.eml`` header rewrite, tested without a case around it."""

    RAW = (
        "From: a@example.com\n"
        "To: b@example.com\n"
        "Date: Fri, 25 Mar 2022 19:00:00 -0000\n"
        "Subject: Probe\n"
        "\n"
        "body text\n"
    )

    def test_the_date_header_is_rewritten_to_fixed_utc(self, tmp_path: Path) -> None:
        path = tmp_path / "probe.eml"
        path.write_text(self.RAW, encoding="utf-8")
        normalize_eml(path, date(2022, 3, 25))
        assert "Date: Fri, 25 Mar 2022 12:00:00 +0000" in path.read_text(encoding="utf-8")

    def test_the_synthetic_header_is_stamped_exactly_once(self, tmp_path: Path) -> None:
        path = tmp_path / "probe.eml"
        path.write_text(self.RAW, encoding="utf-8")
        normalize_eml(path, date(2022, 3, 25))
        normalize_eml(path, date(2022, 3, 25))
        text = path.read_text(encoding="utf-8")
        assert text.count(f"{SYNTHETIC_EML_HEADER}: true") == 1

    def test_the_body_is_untouched(self, tmp_path: Path) -> None:
        path = tmp_path / "probe.eml"
        path.write_text(self.RAW, encoding="utf-8")
        normalize_eml(path, date(2022, 3, 25))
        assert path.read_text(encoding="utf-8").endswith("body text\n")

    def test_normalization_is_idempotent_at_the_byte_level(self, tmp_path: Path) -> None:
        path = tmp_path / "probe.eml"
        path.write_text(self.RAW, encoding="utf-8")
        once = normalize_eml(path, date(2022, 3, 25))
        twice = normalize_eml(path, date(2022, 3, 25))
        assert once == twice


# ---------------------------------------------------------------------------
# Synthetic-data markers
# ---------------------------------------------------------------------------


@requires_substrate
class TestSyntheticMarkers:
    """Every emitted file says what it is, and saying so costs no determinism."""

    @pytest.fixture(scope="class")
    def rendered(self, tmp_path_factory: pytest.TempPathFactory) -> Any:
        seed = parse_case_seed(small_case("marker-probe"))
        return generate_case(seed, tmp_path_factory.mktemp("markers"), case_number=1)

    def _paths(self, rendered: Any, suffix: str) -> list[Path]:
        return sorted((rendered.directory / "documents").glob(f"*{suffix}"))

    def test_pdfs_carry_the_marker_in_subject_and_producer(self, rendered: Any) -> None:
        pdfs = self._paths(rendered, ".pdf")
        assert pdfs
        payload = pdfs[0].read_bytes()
        assert b"/Subject" in payload
        assert b"SYNTHETIC TEST DATA" in payload

    def test_docx_files_carry_the_marker_in_core_properties(self, rendered: Any) -> None:
        docx_files = self._paths(rendered, ".docx")
        if not docx_files:
            pytest.skip("format mix produced no .docx for this seed")
        with zipfile.ZipFile(docx_files[0]) as archive:
            core = archive.read("docProps/core.xml").decode("utf-8")
        assert SYNTHETIC_MARKER in core

    def test_eml_files_carry_the_marker_header(self, rendered: Any) -> None:
        emails = self._paths(rendered, ".eml")
        if not emails:
            pytest.skip("format mix produced no .eml for this seed")
        assert f"{SYNTHETIC_EML_HEADER}: true" in emails[0].read_text(encoding="utf-8")

    def test_markers_are_inside_the_hashed_bytes(self, rendered: Any) -> None:
        """A marker applied after hashing would make every manifest a lie."""
        for entry in rendered.manifest["documents"]:
            path = rendered.directory / "documents" / entry["filename"]
            actual = hashlib.md5(path.read_bytes(), usedforsecurity=False).hexdigest()
            assert actual == entry["md5Checksum"], entry["filename"]


# ---------------------------------------------------------------------------
# The hash-seed guard
# ---------------------------------------------------------------------------


def _generate_in_subprocess(
    spec: Path,
    out: Path,
    hash_seed: str | None,
    extra_env: dict[str, str] | None = None,
) -> None:
    """Run one full generation in a fresh interpreter under *hash_seed*."""
    env = dict(os.environ)
    if hash_seed is None:
        env.pop("PYTHONHASHSEED", None)
    else:
        env["PYTHONHASHSEED"] = hash_seed
    env.update(extra_env or {})
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            REEXEC_MODULE,
            "generate",
            "--spec",
            str(spec),
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]


def _hash_seed_spec(path: Path) -> Path:
    """Write a one-case spec small enough to render twice per test."""
    import yaml

    path.write_text(
        yaml.safe_dump(
            {
                "caseload_id": "hashseed-load",
                "cases": [{**small_case("hs-001"), "documents": {"global_cap": 10}}],
            }
        ),
        encoding="utf-8",
    )
    return path


@requires_substrate
class TestHashSeedGuard:
    """``PYTHONHASHSEED`` is not a boolean, and the guard used to treat it as one.

    The substrate orders content-pool strings through ``list(set(...))``, whose
    iteration order depends on the per-process string-hash salt. Only ``0``
    disables that salt. The old guard returned early for *any* non-empty value,
    so ``PYTHONHASHSEED=1`` and ``PYTHONHASHSEED=2`` were both accepted as
    deliberate determinism choices — and produced two different caseloads from
    one seed. ``random``, which is the default behaviour written out longhand,
    was accepted too.
    """

    def test_two_different_pre_set_hash_seeds_produce_identical_trees(
        self, tmp_path: Path
    ) -> None:
        """The exact reproduction: ``=1`` versus ``=2``, whole tree compared."""
        spec = _hash_seed_spec(tmp_path / "spec.yaml")
        one, two = tmp_path / "seed-one", tmp_path / "seed-two"

        _generate_in_subprocess(spec, one, "1")
        _generate_in_subprocess(spec, two, "2")

        first, second = digest_tree(one), digest_tree(two)
        assert first, "nothing was generated — the probe proves nothing"
        assert set(first) == set(second), "the two runs wrote different files"
        drifted = sorted(name for name in first if first[name] != second[name])
        assert not drifted, (
            f"{len(drifted)} file(s) drifted between PYTHONHASHSEED=1 and =2: {drifted[:10]}"
        )

    def test_a_pre_set_hash_seed_matches_an_unset_one(self, tmp_path: Path) -> None:
        """The pinned path and the re-exec path must land on the same bytes."""
        spec = _hash_seed_spec(tmp_path / "spec.yaml")
        pinned, unset = tmp_path / "pinned", tmp_path / "unset"

        _generate_in_subprocess(spec, pinned, "random")
        _generate_in_subprocess(spec, unset, None)

        first, second = digest_tree(pinned), digest_tree(unset)
        drifted = sorted(name for name in first if first[name] != second[name])
        assert not drifted, f"PYTHONHASHSEED=random drifted from unset: {drifted[:10]}"

    @pytest.mark.parametrize("value", ["1", "2", "random", ""])
    def test_only_zero_is_treated_as_stable(self, value: str) -> None:
        """The predicate the guard branches on, checked directly."""
        previous = os.environ.get("PYTHONHASHSEED")
        try:
            os.environ["PYTHONHASHSEED"] = value
            assert not hashing_is_stable(), f"{value!r} must not count as stable"
            os.environ["PYTHONHASHSEED"] = "0"
            assert hashing_is_stable()
        finally:
            if previous is None:
                os.environ.pop("PYTHONHASHSEED", None)
            else:
                os.environ["PYTHONHASHSEED"] = previous

    def test_a_pre_set_sentinel_does_not_buy_a_bypass(self, tmp_path: Path) -> None:
        """The second review's reproduction: the sentinel outranked the seed.

        ``ensure_stable_hashing`` read :data:`REEXEC_GUARD_VAR` *before* it read
        ``PYTHONHASHSEED``, so anything that pre-set the sentinel — a wrapper
        script, a CI job copying the child's environment, a developer who saw
        the variable and set it — returned early with salted hashing still live.
        Combined with ``PYTHONHASHSEED=1`` versus ``=2`` that is the same drift
        the guard exists to stop, wearing the guard's own badge.

        The sentinel is a loop counter, not a certificate. Only
        ``PYTHONHASHSEED=0`` is a certificate.
        """
        spec = _hash_seed_spec(tmp_path / "spec.yaml")
        one, two = tmp_path / "sentinel-one", tmp_path / "sentinel-two"
        sentinel = {REEXEC_GUARD_VAR: "1"}

        _generate_in_subprocess(spec, one, "1", sentinel)
        _generate_in_subprocess(spec, two, "2", sentinel)

        first, second = digest_tree(one), digest_tree(two)
        assert first, "nothing was generated — the probe proves nothing"
        assert set(first) == set(second), "the two runs wrote different files"
        drifted = sorted(name for name in first if first[name] != second[name])
        assert not drifted, (
            f"{len(drifted)} file(s) drifted with {REEXEC_GUARD_VAR} pre-set "
            f"and PYTHONHASHSEED=1 vs =2: {drifted[:10]}"
        )

    def test_a_sentinel_at_the_hop_cap_fails_loudly_instead_of_looping(self) -> None:
        """Re-execing unconditionally needs a stop, and the stop must be audible.

        One hop is all a correct environment needs: the child gets
        ``PYTHONHASHSEED=0`` and settles. A second hop means the value did not
        stick — a wrapper is overwriting it, or the platform is ignoring it — and
        the only two options left are an infinite exec loop or an error. The
        error names the variable so the wrapper can be found.
        """
        env = dict(os.environ)
        env[REEXEC_GUARD_VAR] = str(MAX_REEXEC_HOPS)
        env["PYTHONHASHSEED"] = "1"
        completed = subprocess.run(
            [sys.executable, "-m", REEXEC_MODULE, "--version"],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        assert completed.returncode != 0, "a wedged hash seed must not exit clean"
        combined = completed.stdout + completed.stderr
        assert "PYTHONHASHSEED" in combined
        assert REEXEC_GUARD_VAR in combined

    def test_one_hop_is_enough_for_a_healthy_environment(self, tmp_path: Path) -> None:
        """The cap must not fire on the ordinary path, or every run breaks."""
        spec = _hash_seed_spec(tmp_path / "spec.yaml")
        _generate_in_subprocess(spec, tmp_path / "healthy", "1")
        assert digest_tree(tmp_path / "healthy"), "the ordinary re-exec path stopped working"

    def test_opting_out_of_the_reexec_warns_that_determinism_is_lost(self) -> None:
        """An opt-out that is silent is an opt-out nobody knows they took."""
        env = dict(os.environ)
        env[DISABLE_REEXEC_VAR] = "1"
        env["PYTHONHASHSEED"] = "1"
        completed = subprocess.run(
            [sys.executable, "-m", REEXEC_MODULE, "--version"],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        assert completed.returncode == 0, completed.stderr[-2000:]
        combined = completed.stdout + completed.stderr
        assert "determinism.reexec_disabled" in combined
        assert "NOT guaranteed" in combined


# ---------------------------------------------------------------------------
# The ``-m`` re-exec form
# ---------------------------------------------------------------------------


class TestModuleEntryPoint:
    """``python -m wc_caseload_engine`` must survive the hash-seed re-exec."""

    def test_the_module_entry_point_exists(self) -> None:
        from wc_caseload_engine import __main__

        assert callable(__main__.main)

    def test_the_module_form_runs_and_reports_its_version(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", REEXEC_MODULE, "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr[-2000:]
        assert "wc-caseload" in completed.stdout

    def test_the_module_form_survives_the_reexec_with_a_pinned_hash_seed(self) -> None:
        """The re-exec happens for real here: PYTHONHASHSEED starts unset."""
        env = {k: v for k, v in os.environ.items() if k != "PYTHONHASHSEED"}
        completed = subprocess.run(
            [sys.executable, "-m", REEXEC_MODULE, "--help"],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        assert completed.returncode == 0, completed.stderr[-2000:]
        assert "taxonomy-check" in completed.stdout

    def test_the_console_script_still_works_after_the_argv_change(self) -> None:
        script = Path(sys.executable).with_name("wc-caseload")
        if not script.exists():
            pytest.skip("console script not installed in this environment")
        env = {k: v for k, v in os.environ.items() if k != "PYTHONHASHSEED"}
        completed = subprocess.run(
            [str(script), "--version"],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        assert completed.returncode == 0, completed.stderr[-2000:]
        assert "wc-caseload" in completed.stdout


# ---------------------------------------------------------------------------
# AJC-61 (M2) — the assertion ledger and its truth digest
# ---------------------------------------------------------------------------


def assertion_case(case_id: str) -> dict[str, Any]:
    """The AJC-60 probe, opted into the M2 assertion layer as well.

    Its own probe for the same reason ``medical_case`` is: the assertion layer
    adds clock-shaped surfaces of its own — sampled report dates are computed
    from the injury date, the validation context carries the anchor, and the
    ledger digest seals every one of them into the truth channel.
    """
    case = medical_case(case_id)
    case["scenario"]["medical_assertions"] = {}
    return case


@requires_substrate
def test_assertion_ledger_and_truth_digest_are_identical_across_timezones(
    tmp_path: Path,
) -> None:
    from wc_caseload_engine.truth_manifest import build_case_truth_manifest

    seed = parse_case_seed(assertion_case("tz-assertions"))

    with timezone_set(ZONE_WEST):
        west_plan = build_case_plan(seed)
        west_truth = build_case_truth_manifest(west_plan)
    with timezone_set(ZONE_EAST):
        east_plan = build_case_plan(seed)
        east_truth = build_case_truth_manifest(east_plan)

    assert west_plan.medical_assertions is not None
    assert east_plan.medical_assertions is not None
    assert (
        west_plan.medical_assertions.model_dump()
        == east_plan.medical_assertions.model_dump()
    ), "the assertion ledger differs between zones"
    west_channel = west_truth["channels"]["assertions"]
    east_channel = east_truth["channels"]["assertions"]
    assert west_channel["ledgerDigest"] == east_channel["ledgerDigest"]
    assert json.dumps(west_truth, sort_keys=True) == json.dumps(
        east_truth, sort_keys=True
    ), "the truth manifest differs between zones"


@requires_substrate
def test_assertion_ledger_digest_is_identical_across_hash_seeded_processes(
    tmp_path: Path,
) -> None:
    """Two fresh interpreters under different PYTHONHASHSEED values must seal
    the same ledger into the same digest — set iteration or dict order leaking
    into composition would land exactly here."""
    import yaml as yaml_module

    spec_path = tmp_path / "assertions.yaml"
    spec_path.write_text(
        yaml_module.safe_dump(
            {
                "caseload_id": "assertion-hashseed",
                "cases": [
                    {**assertion_case("ah-001"), "documents": {"global_cap": 6}}
                ],
            }
        ),
        encoding="utf-8",
    )
    first_out = tmp_path / "first"
    second_out = tmp_path / "second"
    _generate_in_subprocess(spec_path, first_out, hash_seed="0")
    _generate_in_subprocess(spec_path, second_out, hash_seed="424242")

    first_truth = json.loads(
        (first_out / "truth" / "ah-001.truth.json").read_text(encoding="utf-8")
    )
    second_truth = json.loads(
        (second_out / "truth" / "ah-001.truth.json").read_text(encoding="utf-8")
    )
    first_channel = first_truth["channels"]["assertions"]
    second_channel = second_truth["channels"]["assertions"]
    assert first_channel["ledgerDigest"] == second_channel["ledgerDigest"]
    assert json.dumps(first_channel, sort_keys=True) == json.dumps(
        second_channel, sort_keys=True
    )


# ---------------------------------------------------------------------------
# AJC-62 (M3) — complete medical-story determinism observations
# ---------------------------------------------------------------------------


def _assert_medical_story_matrix_pins() -> None:
    """R65 literals live beside their consumers; production cannot self-pin."""
    assert MEDICAL_STORY_TZ_MATRIX == (
        "America/Los_Angeles",
        "Australia/Sydney",
    )
    assert MEDICAL_STORY_HASH_SEEDS == ("0", "424242")
    assert MEDICAL_STORY_REPEAT_GENERATIONS == 2


@requires_substrate
def test_medical_story_plan_and_output_are_identical_across_timezones(
    tmp_path: Path,
) -> None:
    """R65's two-zone perturbation over all seven frozen observation fields."""
    _assert_medical_story_matrix_pins()
    observations: dict[str, dict[str, Any]] = {}
    for zone in MEDICAL_STORY_TZ_MATRIX:
        with timezone_set(zone):
            observations[zone] = _medical_story_observation(tmp_path / zone)
    _assert_medical_story_observations_equal(observations)


@requires_substrate
def test_medical_story_plan_and_output_are_identical_across_hash_seeded_processes(
    tmp_path: Path,
) -> None:
    """R65's two real hash salts over plan, bindings, truth, bytes, and trace."""
    _assert_medical_story_matrix_pins()
    observations = {
        hash_seed: _medical_story_observation_in_subprocess(
            tmp_path / f"hash-{hash_seed}", hash_seed
        )
        for hash_seed in MEDICAL_STORY_HASH_SEEDS
    }
    _assert_medical_story_observations_equal(observations)


@requires_substrate
def test_medical_story_repeated_generation_is_byte_identical(
    tmp_path: Path,
) -> None:
    """R65's exact repeat count over the same complete observation contract."""
    _assert_medical_story_matrix_pins()
    observations = {
        f"repeat-{index}": _medical_story_observation(tmp_path / f"repeat-{index}")
        for index in range(MEDICAL_STORY_REPEAT_GENERATIONS)
    }
    _assert_medical_story_observations_equal(observations)
