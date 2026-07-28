"""The two entrypoints produce the same bytes (ISC-12).

``wc-caseload`` and ``python -m wc_caseload_engine`` are not two spellings of
one thing. :func:`~wc_caseload_engine.determinism.ensure_stable_hashing`
re-executes the interpreter to pin ``PYTHONHASHSEED``, and a re-exec has to
reconstruct the command line it was launched with — a console script and a
``-m`` start reconstruct differently. Forge flagged during review that the
``-m`` form is not preserved across that re-exec; this file is the assertion
that the difference does not reach the output.

Byte-identity across entrypoints is the sharp version of the determinism claim
for the same reason cross-timezone identity was: repeating a run through the
same door proves the door is consistent with itself, which is not the property
anyone depends on.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from conftest import requires_substrate

pytestmark = requires_substrate

CONSOLE_SCRIPT = Path(sys.executable).parent / "wc-caseload"

SMALL_CASE = {
    "case_id": "entrypoint-001",
    "rng_seed": 31337,
    "injury": {
        "type": "specific",
        "date_of_injury": "2022-09-09",
        "body_parts": [{"part": "shoulder", "icd10": "M75.100"}],
    },
    "lifecycle": {"target_stage": "resolved", "resolution": {"type": "c_and_r"}},
    "documents": {"global_cap": 8},
}


def _digest_tree(root: Path) -> dict[str, str]:
    """``relative path -> sha256`` for every file under *root*."""
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _write_spec(path: Path) -> None:
    path.write_text(
        yaml.safe_dump({"caseload_id": "entrypoint-load", "cases": [SMALL_CASE]}),
        encoding="utf-8",
    )


def _generate(command: list[str], spec: Path, out: Path) -> None:
    completed = subprocess.run(
        [*command, "generate", "--spec", str(spec), "--out", str(out)],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ},
    )
    assert completed.returncode == 0, completed.stderr[-2000:]


def test_the_console_script_is_installed() -> None:
    """Guards the comparison: a missing script would skip the real entrypoint."""
    assert CONSOLE_SCRIPT.is_file(), (
        f"{CONSOLE_SCRIPT} not found — install the package with `uv pip install -e .`"
    )


def test_module_and_console_entrypoints_produce_identical_bytes(tmp_path: Path) -> None:
    """The headline parity assertion: same seed, two doors, same files."""
    spec = tmp_path / "spec.yaml"
    _write_spec(spec)

    module_out = tmp_path / "module"
    script_out = tmp_path / "script"
    _generate([sys.executable, "-m", "wc_caseload_engine"], spec, module_out)
    _generate([str(CONSOLE_SCRIPT)], spec, script_out)

    module_digests = _digest_tree(module_out)
    script_digests = _digest_tree(script_out)

    assert set(module_digests) == set(script_digests), (
        "the entrypoints wrote different files: "
        f"{sorted(set(module_digests) ^ set(script_digests))[:10]}"
    )
    drifted = sorted(
        name for name in module_digests if module_digests[name] != script_digests[name]
    )
    assert not drifted, f"{len(drifted)} file(s) differ between entrypoints: {drifted[:10]}"
    assert len(module_digests) > 8, "too few files written to call this a comparison"


def test_the_cli_module_form_also_works(tmp_path: Path) -> None:
    """``-m wc_caseload_engine.cli`` is a third door and must agree too."""
    spec = tmp_path / "spec.yaml"
    _write_spec(spec)

    package_out = tmp_path / "package"
    module_out = tmp_path / "cli-module"
    _generate([sys.executable, "-m", "wc_caseload_engine"], spec, package_out)
    _generate([sys.executable, "-m", "wc_caseload_engine.cli"], spec, module_out)

    assert _digest_tree(package_out) == _digest_tree(module_out)


def _version_line(stdout: str) -> str:
    """The ``wc-caseload, version X`` line, without structlog's timestamped noise.

    Both entrypoints emit a ``determinism.reexec`` debug record on the way
    through, and it names the launcher — which differs by design. Comparing raw
    stdout would compare the launchers; this compares what was asked for.
    """
    lines = [line for line in stdout.splitlines() if "version" in line and "[" not in line]
    assert len(lines) == 1, f"expected one version line, got {lines}"
    return lines[0].strip()


def test_both_entrypoints_report_the_same_version() -> None:
    """A version skew would explain a byte difference and hide a real one."""
    module = subprocess.run(
        [sys.executable, "-m", "wc_caseload_engine", "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    script = subprocess.run(
        [str(CONSOLE_SCRIPT), "--version"], capture_output=True, text=True, check=True
    )
    assert _version_line(module.stdout) == _version_line(script.stdout)


@pytest.mark.parametrize("entrypoint", ["module", "script"])
def test_validate_passes_on_output_from_either_entrypoint(
    tmp_path: Path, entrypoint: str
) -> None:
    """Whichever door generated it, the tree validates with zero fallbacks."""
    spec = tmp_path / "spec.yaml"
    _write_spec(spec)
    out = tmp_path / entrypoint
    command = (
        [sys.executable, "-m", "wc_caseload_engine"]
        if entrypoint == "module"
        else [str(CONSOLE_SCRIPT)]
    )
    _generate(command, spec, out)

    completed = subprocess.run(
        [*command, "validate", "--out", str(out)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr[-2000:]
    assert "fallbacks : 0" in completed.stdout, completed.stdout
