"""The golden-corpus gate, and the reasons to believe it.

``tools/golden_gate.py`` is the first guard in this package that watches output
across *time* rather than within a run. The existing determinism suites generate
the same spec twice and compare the two — which proves the machinery has no leak
today, and says nothing about whether today still matches last month. This gate
answers that, so it is worth being precise about what it can and cannot see.

The slow probe at the bottom is the gate itself: regenerate the ``suite``-tier
corpora and compare with the committed goldens. Everything above it is cheaper
and, between them, the reason the slow one means anything:

* the digest is **faithful** — it stands in for the file's own bytes, checked by
  round-tripping every real manifest the demo caseload produced;
* the digest is **sensitive** — a moved checksum, a reordered document list or a
  changed ledger all move it;
* the digest is **tolerant of exactly two things** — the engine version string
  and the substrate SHA, which are recorded as context rather than digested;
* the redaction paths are **checked, not assumed** — a manifest that stops
  carrying ``provenance.substrateSha`` makes the tool raise rather than quietly
  digest a different shape and report clean.

That last one is the failure mode this file exists for. A gate that silently
measures the wrong thing and passes is worse than no gate, because it also
retires the suspicion that would have found the drift.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import copy
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from conftest import requires_substrate

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from golden_gate import (
    AXES,
    CASE_REDACTIONS,
    CI_TIER,
    CORPORA,
    EXAMPLES,
    GOLDEN_FORMAT,
    PACKAGE,
    SUITE_TIER,
    Corpus,
    GoldenError,
    canonical_json_bytes,
    compare,
    documents_digest,
    normalized_manifest_digest,
)

TOOL = PACKAGE / "tools" / "golden_gate.py"

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
"""What every digest in a golden has to look like."""


def _demo_manifest_paths(demo_caseload: Path) -> list[Path]:
    """Every case manifest of the shared demo caseload."""
    return sorted(demo_caseload.glob("*/manifest.json"))


def _write_json(path: Path, payload: Any) -> Path:
    """Write *payload* the way the engine writes a manifest."""
    path.write_bytes(canonical_json_bytes(payload))
    return path


# ---------------------------------------------------------------------------
# The registry covers what is shipped
# ---------------------------------------------------------------------------


def test_every_shipped_example_spec_is_a_registered_corpus() -> None:
    """A new ``examples/*.yaml`` is gated, or this test says so.

    The gate is only as wide as its registry, and a registry maintained by
    memory is a registry that drifts. Adding a showcase without a golden should
    cost one second of test time to discover, not one release.
    """
    on_disk = {path.stem for path in EXAMPLES.glob("*.yaml")}
    registered = {corpus.name for corpus in CORPORA}
    assert on_disk == registered, (
        f"examples/ and CORPORA disagree — unregistered: {sorted(on_disk - registered)}, "
        f"registered but absent: {sorted(registered - on_disk)}"
    )


def test_every_registered_corpus_is_in_exactly_one_tier() -> None:
    """Every corpus is gated once: by the suite or by the CI step, never neither."""
    for corpus in CORPORA:
        assert corpus.tier in (SUITE_TIER, CI_TIER), f"{corpus.name}: tier {corpus.tier!r}"
    tiers = {corpus.tier for corpus in CORPORA}
    assert tiers == {SUITE_TIER, CI_TIER}, (
        "both tiers must be populated — an empty tier means one of the two gates "
        f"runs nothing, and the tiers present are {sorted(tiers)}"
    )


def test_every_registered_corpus_has_a_well_formed_golden() -> None:
    """The goldens are committed, current-format, and internally consistent."""
    for corpus in CORPORA:
        assert corpus.golden.is_file(), (
            f"{corpus.name}: no committed golden. Record one with "
            f"`python tools/golden_gate.py --record --only {corpus.name}`"
        )
        golden = json.loads(corpus.golden.read_text(encoding="utf-8"))
        assert golden["format"] == GOLDEN_FORMAT
        assert golden["corpus"] == corpus.name
        assert golden["tier"] == corpus.tier
        assert golden["spec"] == corpus.spec.relative_to(PACKAGE).as_posix()

        cases = golden["cases"]
        assert cases, f"{corpus.name}: golden records no cases"
        assert golden["caseCount"] == len(cases)
        assert golden["documentCount"] == sum(case["documentCount"] for case in cases.values())
        assert SHA256_RE.match(golden["caseload"])
        for case_id, case in cases.items():
            for axis, _label in AXES:
                assert SHA256_RE.match(case[axis]), f"{corpus.name}/{case_id}: bad {axis} digest"
            assert case["documentCount"] > 0
            assert 0 < case["distinctSubtypes"] <= case["documentCount"]


def test_a_golden_records_the_provenance_needed_to_explain_a_drift() -> None:
    """The recording environment is captured, or a red gate cannot be diagnosed."""
    for corpus in CORPORA:
        recorded = json.loads(corpus.golden.read_text(encoding="utf-8"))["recordedWith"]
        assert recorded["engine"]
        assert recorded["python"]
        # The versions that actually decide rendered bytes. ReportLab lays the
        # PDFs out; when a corpus drifts for no reason in the diff, this is
        # usually where the reason is.
        assert recorded["dependencies"]["reportlab"] != "not-installed"


# ---------------------------------------------------------------------------
# The digest is faithful
# ---------------------------------------------------------------------------


@requires_substrate
def test_the_normalizer_reproduces_every_demo_manifest_byte_for_byte(
    demo_caseload: Path,
) -> None:
    """A digest may only stand in for a file it can reproduce.

    The tool digests a *parsed and re-serialized* manifest so it can neutralize
    two volatile fields. That is only honest if the round trip is lossless — a
    reformatted float or a mangled character would mean the digest describes
    something the file is not. Checked against every manifest the demo caseload
    actually produces rather than a constructed sample.
    """
    paths = _demo_manifest_paths(demo_caseload)
    assert paths, "the demo caseload produced no manifests"
    for path in paths:
        raw = path.read_bytes()
        assert canonical_json_bytes(json.loads(raw)) == raw, f"{path}: round trip is lossy"


def test_a_manifest_the_normalizer_cannot_reproduce_is_refused(tmp_path: Path) -> None:
    """Compact JSON is not what the engine writes, so it is not silently digested."""
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"provenance": {"generator": "x", "substrateSha": "y"}}))
    with pytest.raises(GoldenError, match="byte-for-byte"):
        normalized_manifest_digest(path, CASE_REDACTIONS)


# ---------------------------------------------------------------------------
# The digest is sensitive to content and tolerant of provenance
# ---------------------------------------------------------------------------


@requires_substrate
def test_the_digest_ignores_provenance_and_notices_content(
    demo_caseload: Path, tmp_path: Path
) -> None:
    """The two halves of the design claim, on one real manifest.

    Tolerance without sensitivity is a gate that passes everything; sensitivity
    without tolerance is a gate that fails on a version bump. Both directions
    are asserted here because either one alone is satisfiable by a broken
    implementation.
    """
    source = _demo_manifest_paths(demo_caseload)[0]
    baseline = normalized_manifest_digest(source, CASE_REDACTIONS)
    payload = json.loads(source.read_text(encoding="utf-8"))

    moved_provenance = copy.deepcopy(payload)
    moved_provenance["provenance"]["substrateSha"] = "0" * 40
    moved_provenance["provenance"]["generator"] = "wc-synthetic-caseload-engine@99.0.0"
    assert (
        normalized_manifest_digest(
            _write_json(tmp_path / "provenance.json", moved_provenance), CASE_REDACTIONS
        )
        == baseline
    ), "a version or substrate-SHA change must not read as corpus drift"

    moved_checksum = copy.deepcopy(payload)
    moved_checksum["documents"][0]["md5Checksum"] = "0" * 32
    assert (
        normalized_manifest_digest(
            _write_json(tmp_path / "checksum.json", moved_checksum), CASE_REDACTIONS
        )
        != baseline
    ), "a moved document checksum must read as corpus drift"

    moved_ledger = copy.deepcopy(payload)
    moved_ledger["caseFacts"]["treatment"]["status"] = "probe-value"
    assert (
        normalized_manifest_digest(
            _write_json(tmp_path / "ledger.json", moved_ledger), CASE_REDACTIONS
        )
        != baseline
    ), "a moved ledger fact must read as corpus drift"


@requires_substrate
def test_a_stale_redaction_path_raises_instead_of_digesting_a_different_shape(
    demo_caseload: Path, tmp_path: Path
) -> None:
    """The redaction paths are checked against the manifest, not assumed.

    If ``provenance.substrateSha`` is ever renamed or dropped, this tool would
    go on digesting happily — and would then be digesting the *unredacted*
    provenance, which moves per checkout, so the gate would fail everywhere for
    a reason nobody could read. Raising is the only outcome that leads anywhere.
    """
    payload = json.loads(_demo_manifest_paths(demo_caseload)[0].read_text(encoding="utf-8"))
    del payload["provenance"]["substrateSha"]
    path = _write_json(tmp_path / "manifest.json", payload)
    with pytest.raises(GoldenError, match="substrateSha"):
        normalized_manifest_digest(path, CASE_REDACTIONS)


@requires_substrate
def test_the_documents_digest_moves_with_content_and_with_order(
    demo_caseload: Path,
) -> None:
    """Both are real drift: a changed file, and the same files in a new order."""
    manifest = json.loads(_demo_manifest_paths(demo_caseload)[0].read_text(encoding="utf-8"))
    documents = manifest["documents"]
    baseline = documents_digest(documents, "probe")

    changed = copy.deepcopy(documents)
    changed[0]["md5Checksum"] = "0" * 32
    assert documents_digest(changed, "probe") != baseline

    renamed = copy.deepcopy(documents)
    renamed[0]["filename"] = "renamed.pdf"
    assert documents_digest(renamed, "probe") != baseline

    assert documents_digest(list(reversed(documents)), "probe") != baseline

    dropped = copy.deepcopy(documents)[:-1]
    assert documents_digest(dropped, "probe") != baseline


def test_a_document_entry_without_a_checksum_is_an_error() -> None:
    """A manifest that cannot supply the pair is not silently digested as empty."""
    with pytest.raises(GoldenError, match="filename/md5Checksum"):
        documents_digest([{"filename": "a.pdf"}], "probe")


# ---------------------------------------------------------------------------
# The report says what drifted
# ---------------------------------------------------------------------------


def _golden_stub(**cases: dict[str, Any]) -> dict[str, Any]:
    """A minimal golden payload for exercising :func:`compare`."""
    return {
        "caseCount": len(cases),
        "documentCount": sum(case["documentCount"] for case in cases.values()),
        "caseload": "c" * 64,
        "cases": cases,
    }


def _case_stub(**overrides: Any) -> dict[str, Any]:
    """One recorded case, all four axes present."""
    case = {
        "documentCount": 3,
        "distinctSubtypes": 2,
        "documents": "d" * 64,
        "manifest": "m" * 64,
        "seed": "s" * 64,
        "facts": "f" * 64,
    }
    case.update(overrides)
    return case


def test_the_report_names_the_axis_that_drifted() -> None:
    """"Something changed" is not a finding; "the seed changed" is."""
    corpus = CORPORA[0]
    golden = _golden_stub(alpha=_case_stub())
    for axis, label in AXES:
        fresh = _golden_stub(alpha=_case_stub(**{axis: "9" * 64}))
        problems = compare(corpus, golden, fresh)
        assert any(label in problem and "alpha" in problem for problem in problems), (
            f"a drifted {axis} digest was not reported as {label!r}: {problems}"
        )


def test_the_report_names_added_and_missing_cases() -> None:
    """A corpus that gained or lost a case is a shape change, reported as one."""
    corpus = CORPORA[0]
    golden = _golden_stub(alpha=_case_stub())
    fresh = _golden_stub(beta=_case_stub())
    problems = compare(corpus, golden, fresh)
    assert any("alpha" in problem and "did not produce" in problem for problem in problems)
    assert any("beta" in problem and "absent from the golden" in problem for problem in problems)


def test_the_report_names_a_changed_document_count_in_plain_numbers() -> None:
    """A count is a diagnosis; a digest is only a symptom."""
    corpus = CORPORA[0]
    golden = _golden_stub(alpha=_case_stub())
    fresh = _golden_stub(alpha=_case_stub(documentCount=4, documents="9" * 64))
    problems = compare(corpus, golden, fresh)
    assert any("documents 3 recorded, 4 now" in problem for problem in problems)


def test_an_identical_pair_reports_nothing() -> None:
    """The gate has to be able to say yes, or it is not a gate."""
    golden = _golden_stub(alpha=_case_stub())
    assert compare(CORPORA[0], golden, copy.deepcopy(golden)) == []


def test_an_unknown_corpus_name_is_a_usage_error_not_an_empty_pass() -> None:
    """``--only typo`` must not check zero corpora and exit clean."""
    completed = subprocess.run(
        [sys.executable, str(TOOL), "--check", "--only", "no-such-corpus"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2, completed.stdout + completed.stderr
    assert "unknown corpus" in completed.stderr


def test_a_missing_golden_is_reported_with_the_command_that_creates_it(
    tmp_path: Path,
) -> None:
    """A gate that cannot find its baseline explains itself."""
    from golden_gate import _load_golden

    absent = Corpus(name="not-a-corpus", tier=SUITE_TIER, why="probe")
    with pytest.raises(GoldenError, match="--record --only not-a-corpus"):
        _load_golden(absent)


# ---------------------------------------------------------------------------
# The gate itself
# ---------------------------------------------------------------------------


@pytest.mark.slow
@requires_substrate
def test_the_suite_tier_corpora_are_byte_identical_to_their_goldens() -> None:
    """The invariant, enforced: same seed and engine, same bytes as when recorded.

    Regenerates the ``suite``-tier corpora through the shipped CLI in fresh
    processes and compares every digest with the committed golden. The
    ``ci``-tier corpora are covered by their own CI step so that this stays
    around half a minute; see ``CORPORA`` for why the split is drawn there.

    A failure here is not a flake. Either something changed the output — in
    which case the report says which case and which axis — or a dependency
    moved, which the report also says. If the change was intended, re-record and
    commit the golden so the diff is reviewable.
    """
    completed = subprocess.run(
        [sys.executable, str(TOOL), "--check", "--tier", SUITE_TIER],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout[-6000:] + completed.stderr[-2000:]
