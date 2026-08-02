"""The gate gets the treatment it gives everything else.

`tools/mutation_gate.py` is now the thing certifying every other fix in this
package, and its first version certified ten mutants that never ran a test. It
treated any non-zero pytest exit as proof: ten registry entries named classes
that do not exist, pytest exited 4 with nothing collected, and all ten scored
RED. The reported 100/100 was 90/100.

That is a guard which does not cover its own claim — the exact defect class the
gate was built to catch, in the gate. So the gate needs the same discipline: a
probe per way a pytest run can end, asserting that only one of them is allowed
to mean "the guard caught its defect".

Every case here runs a real pytest subprocess against a two-file throwaway
package in `tmp_path`, because the thing under test *is* the subprocess
protocol. Mocking the report would test the reading and skip the writing, and
the writing is where the first version went wrong.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from mutation_gate import (
    REGISTRY,
    Mutant,
    load,
    partition,
    preflight,
    run_one,
    shard,
)

#: The throwaway source a probe mutates. Every scenario below is one edit to it.
_SOURCE = '''\
VALUE = 1
SKIP = False
INTERRUPT = False


def setup_value():
    return VALUE


def teardown_value():
    return VALUE
'''

#: The throwaway guard. It asserts the source's claim and offers the fixture
#: seams a setup/teardown scenario needs.
_GUARD = '''\
import pytest

import subject


@pytest.fixture
def prepared():
    value = subject.setup_value()
    yield value
    subject.teardown_value()


class TestTheClaim:
    def test_the_value_is_one(self, prepared):
        if subject.SKIP:
            pytest.skip("the source asked for it")
        if subject.INTERRUPT:
            raise KeyboardInterrupt
        assert prepared.bit_length() == 1
        assert subject.VALUE == 1
'''


@pytest.fixture
def probe(tmp_path: Path) -> Path:
    """A two-file package whose guard passes before anything is mutated."""
    (tmp_path / "subject.py").write_text(_SOURCE)
    (tmp_path / "test_probe.py").write_text(_GUARD)
    return tmp_path


def _mutant(
    root: Path,
    replace: str,
    *,
    find: str = "VALUE = 1",
    node: str | None = None,
) -> Mutant:
    return Mutant(
        id="probe",
        title="a probe",
        path=root / "subject.py",
        find=find,
        replace=replace,
        test=node or "test_probe.py::TestTheClaim::test_the_value_is_one",
        root=root,
    )


class TestOnlyANamedCallPhaseAssertionIsRed:
    """Eleven ways a run can end, and exactly one of them is evidence."""

    def test_an_assertion_failure_in_the_call_phase_is_red(self, probe: Path) -> None:
        verdict = run_one(_mutant(probe, "VALUE = 2"), python=sys.executable)
        assert verdict.token == "RED", verdict
        assert verdict.proved

    def test_a_guard_that_still_passes_is_survived(self, probe: Path) -> None:
        verdict = run_one(
            _mutant(probe, "VALUE = 1  # unchanged"), python=sys.executable
        )
        assert verdict.token == "SURVIVED", verdict
        assert not verdict.proved

    def test_a_node_id_that_names_nothing_is_not_red(self, probe: Path) -> None:
        """The defect that made the gate lie about ten mutants.

        pytest exits 4 and prints a usage error; the old gate saw non-zero and
        certified it.
        """
        verdict = run_one(
            _mutant(probe, "VALUE = 2", node="test_probe.py::TestNoSuchClass::test_x"),
            python=sys.executable,
        )
        assert verdict.token == "NO-TEST", verdict
        assert not verdict.proved

    def test_a_collection_error_is_not_red(self, probe: Path) -> None:
        """The mutated module raises on import, so the guard never runs."""
        verdict = run_one(_mutant(probe, "VALUE = 1 // 0"), python=sys.executable)
        assert verdict.token in {"NO-TEST", "COLLECT-ERROR"}, verdict
        assert not verdict.proved

    def test_a_mutation_that_does_not_compile_is_not_red(self, probe: Path) -> None:
        verdict = run_one(_mutant(probe, "VALUE = ("), python=sys.executable)
        assert verdict.token == "INVALID-MUTATION", verdict
        assert not verdict.proved

    def test_a_setup_failure_is_named_as_one(self, probe: Path) -> None:
        (probe / "subject.py").write_text(
            _SOURCE.replace(
                "def setup_value():\n    return VALUE",
                "def setup_value():\n    return VALUE  # seam",
            )
        )
        verdict = run_one(
            _mutant(
                probe,
                "def setup_value():\n    raise RuntimeError('fixture')",
                find="def setup_value():\n    return VALUE  # seam",
            ),
            python=sys.executable,
        )
        assert verdict.token == "SETUP-ERROR", verdict

    def test_a_teardown_failure_is_named_as_one(self, probe: Path) -> None:
        verdict = run_one(
            _mutant(
                probe,
                "def teardown_value():\n    raise RuntimeError('teardown')",
                find="def teardown_value():\n    return VALUE",
            ),
            python=sys.executable,
        )
        assert verdict.token == "TEARDOWN-ERROR", verdict

    def test_a_skipped_guard_is_not_red(self, probe: Path) -> None:
        verdict = run_one(
            _mutant(probe, "SKIP = True", find="SKIP = False"), python=sys.executable
        )
        assert verdict.token == "SKIPPED", verdict

    def test_an_interrupt_is_not_red(self, probe: Path) -> None:
        verdict = run_one(
            _mutant(probe, "INTERRUPT = True", find="INTERRUPT = False"),
            python=sys.executable,
        )
        assert verdict.token == "PYTEST-EXIT-2", verdict

    def test_a_raw_exception_is_not_red(self, probe: Path) -> None:
        """An ``AttributeError`` out of a broken mutation is not a guard firing."""
        verdict = run_one(_mutant(probe, "VALUE = 'one'"), python=sys.executable)
        assert verdict.token == "ERROR-AttributeError", verdict
        assert not verdict.proved

    def test_a_guard_that_is_already_failing_proves_nothing(self, probe: Path) -> None:
        (probe / "subject.py").write_text(_SOURCE.replace("VALUE = 1", "VALUE = 9"))
        verdict = run_one(
            _mutant(probe, "VALUE = 8", find="VALUE = 9"), python=sys.executable
        )
        assert verdict.token == "GUARD-NOT-GREEN", verdict

    def test_a_mutation_that_no_longer_applies_is_a_finding(self, probe: Path) -> None:
        verdict = run_one(
            _mutant(probe, "VALUE = 2", find="VALUE = 42"), python=sys.executable
        )
        assert verdict.token == "PATCH-MISS", verdict


class TestTheRegistryItselfIsSound:
    """Preflight, run before any campaign — and over the real registry."""

    def test_every_registered_guard_collects_exactly_once(self) -> None:
        """The ten broken node IDs, stated as a standing assertion.

        Ten entries named ``TestTheNamedMethodIsGroundTruth`` and
        ``TestTheLedgerPublishesOnlyWhatADocumentRenders``; the real classes are
        ``TestTheNamedMethod`` and ``TestPublication``. Nothing checked, so all
        ten scored green for as long as they existed.
        """
        problems = preflight(load())
        assert not problems, "\n".join(problems)

    def test_every_mutated_source_compiles(self) -> None:
        """A mutation must be valid Python or it proves the parser works.

        Four entries did not compile or crashed on a type: one replaced ``try``
        with ``if`` and left the ``except`` behind.
        """
        broken: list[str] = []
        for mutant in load():
            original = mutant.path.read_text()
            if original.count(mutant.find) != 1:
                continue  # PATCH-MISS is the campaign's finding, not this one's
            mutated = original.replace(mutant.find, mutant.replace, 1)
            try:
                compile(mutated, str(mutant.path), "exec")
            except SyntaxError as exc:
                broken.append(f"{mutant.id}: {exc.msg} at line {exc.lineno}")
        assert not broken, "\n".join(broken)

    def test_every_registered_mutation_applies_exactly_once(self) -> None:
        misses = [
            f"{m.id}: {m.relative} contains its find text {m.path.read_text().count(m.find)} times"
            for m in load()
            if m.path.read_text().count(m.find) != 1
        ]
        assert not misses, "\n".join(misses)


class TestAShardCannotPassVacuously:
    """``--shard 11/10`` printed "0/0 mutants" and exited 0."""

    def test_an_out_of_range_shard_fails(self) -> None:
        """Rejected *cleanly* — the crash is part of the defect, not the verdict.

        With the range check removed, ``3/0`` reaches ``position % 0`` and
        raises ``ZeroDivisionError``. That is a real failure mode of the defect,
        but letting it escape makes this probe a test error rather than a test
        failure, and to the mutation gate a raw exception is not evidence about
        a defect at all. Caught here so the verdict comes from the guard.
        """
        mutants = load()
        for spec in ("11/10", "0/10", "-1/10", "3/0"):
            try:
                with pytest.raises(SystemExit):
                    shard(mutants, spec)
            except Exception as exc:
                if isinstance(exc, pytest.fail.Exception):
                    raise
                pytest.fail(
                    f"--shard {spec} raised {type(exc).__name__} instead of being "
                    f"refused: {exc}"
                )

    def test_a_malformed_shard_fails(self) -> None:
        mutants = load()
        for spec in ("half", "1/", "/10", "1/2/3", "one/two"):
            with pytest.raises(SystemExit):
                shard(mutants, spec)

    def test_an_empty_selection_fails(self) -> None:
        """More shards than mutants: the tail shards select nothing."""
        two = load()[:2]
        with pytest.raises(SystemExit, match="selects no mutant"):
            shard(two, "3/3")

    def test_ten_shards_partition_the_registry_exactly_once(self) -> None:
        mutants = load()
        shards = partition(mutants, 10)
        assert all(shards), "a shard selected nothing"
        seen: list[str] = [m.id for group in shards for m in group]
        assert len(seen) == len(mutants), (len(seen), len(mutants))
        assert sorted(seen) == sorted(m.id for m in mutants)
        assert len(set(seen)) == len(seen), "a mutant appears in two shards"


class TestTheRegistryFileIsWellFormed:
    def test_the_registry_loads_and_names_live_files(self) -> None:
        mutants = load()
        assert len(mutants) > 90, len(mutants)
        assert len({m.id for m in mutants}) == len(mutants)
        assert REGISTRY.exists()
