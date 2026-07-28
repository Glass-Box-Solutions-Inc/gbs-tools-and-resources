"""The two anti-criteria, probed hard enough to be able to fail.

ISC-73 and ISC-74 were both previously evidenced by observation — "`git status`
shows no writes" and "Faker-sourced cast only". Both statements were true and
neither was a test: the first only watched the repository working tree, which
is not where a stray write lands, and the second was asserted about the
generator rather than measured on its output.

* :func:`test_generation_writes_nothing_outside_the_output_directory` gives the
  process a sandboxed ``HOME``, ``TMPDIR`` and XDG cache, snapshots every one
  of them, generates, and re-snapshots. A temp file, a font cache or a
  dotfile all land inside the monitored tree and all fail the test.
* The denylist sweep reads the *rendered documents* and looks for the names of
  real organizations, which is the only way to catch the leak that actually
  existed: the substrate's carrier and firm pools are real companies, and
  every seed that did not name its own carrier drew one.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

from conftest import (
    NON_TEXT_FORMATS,
    extract_text,
    iter_documents,
    requires_substrate,
)
from wc_caseload_engine.case_context import (
    SYNTHETIC_PROVENANCE,
    synthetic_carrier_name,
    synthetic_firm_name,
)
from wc_caseload_engine.seeds import parse_case_seed

pytestmark = requires_substrate

DENYLIST_PATH = Path(__file__).parent / "data" / "name_denylist.txt"

CAST_IDENTITY_FIELDS = (
    "applicant",
    "employer",
    "carrier",
    "applicantFirm",
    "defenseFirm",
    "judge",
)
"""Manifest fields naming a person or organization.

Checked directly as well as through document text, because 75 of the demo's 331
documents are scanned PDFs whose text cannot be extracted. The manifest carries
the same identities those rasters were rendered from, so the identity surface
stays fully covered even where the text surface cannot reach.
"""


def _load_denylist() -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Parse the denylist into ``(denied, allowed)`` name tuples."""
    denied: list[str] = []
    allowed: list[str] = []
    for raw in DENYLIST_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("ALLOW "):
            allowed.append(line.removeprefix("ALLOW ").strip().lower())
        else:
            denied.append(line.lower())
    return tuple(denied), tuple(allowed)


DENIED_NAMES, ALLOWED_NAMES = _load_denylist()


def _hits(haystack: str) -> list[str]:
    """Denylist names present in *haystack*, ignoring allowed exceptions."""
    lowered = haystack.lower()
    return [name for name in DENIED_NAMES if name in lowered]


# ---------------------------------------------------------------------------
# ISC-73 — no real names in generated output
# ---------------------------------------------------------------------------


def test_the_denylist_is_loaded_and_non_trivial() -> None:
    """Guards the probe: an empty denylist would make every sweep below pass."""
    assert len(DENIED_NAMES) >= 25, f"denylist has only {len(DENIED_NAMES)} entries"
    assert "martinez & associates" in ALLOWED_NAMES
    assert "martinez & associates" not in DENIED_NAMES


def test_the_denylist_would_catch_a_real_name() -> None:
    """The probe must fire on a positive control, or it proves nothing."""
    assert _hits("Prepared by Bradford & Barthel LLP for the carrier")
    assert _hits("claim administered by State Compensation Insurance Fund")
    assert not _hits("Prepared by Martinez & Associates, APC")


def test_no_demo_document_names_a_real_organization(
    demo_manifests: dict[str, dict[str, Any]],
) -> None:
    """Sweep every text-bearing demo document for real carriers and firms."""
    offences: list[str] = []
    scanned = 0
    scanned_text = 0

    for case_id, manifest in sorted(demo_manifests.items()):
        for entry, path in iter_documents(manifest):
            if entry["format"] in NON_TEXT_FORMATS:
                scanned += 1
                continue
            text = extract_text(path, entry["format"])
            if not text.strip():
                continue
            scanned_text += 1
            for name in _hits(text):
                offences.append(f"{case_id}/{entry['filename']}: {name!r}")

    assert scanned_text > 200, f"only {scanned_text} documents yielded text — probe is not running"
    assert not offences, f"{len(offences)} real-organization hit(s): {offences[:20]}"


def test_no_demo_cast_names_a_real_organization(
    demo_manifests: dict[str, dict[str, Any]],
) -> None:
    """The identity surface, checked where scanned PDFs cannot be read."""
    offences: list[str] = []
    for case_id, manifest in sorted(demo_manifests.items()):
        for field_name in CAST_IDENTITY_FIELDS:
            value = str(manifest.get(field_name, ""))
            for name in _hits(value):
                offences.append(f"{case_id}.{field_name} = {value!r} matches {name!r}")
    assert not offences, offences


def test_coined_organization_names_never_collide_with_the_denylist() -> None:
    """Every name the engine can coin, checked against the list once."""
    offences: list[str] = []
    for rng_seed in range(200):
        seed = parse_case_seed(
            {
                "case_id": f"coined-{rng_seed:03d}",
                "rng_seed": rng_seed,
                "injury": {
                    "type": "specific",
                    "date_of_injury": "2023-01-05",
                    "body_parts": [{"part": "knee", "icd10": "M23.51"}],
                },
            }
        )
        for coined in (
            synthetic_carrier_name(seed),
            synthetic_firm_name(seed, "defense_firm"),
        ):
            for name in _hits(coined):
                offences.append(f"{coined!r} matches {name!r}")
    assert not offences, offences


def test_zero_real_pii_is_computed_from_cast_provenance(
    demo_manifests: dict[str, dict[str, Any]],
) -> None:
    """The flag must be derived, and the derivation must be visible."""
    for case_id, manifest in sorted(demo_manifests.items()):
        provenance = manifest["provenance"]
        cast_provenance = provenance["castProvenance"]
        assert cast_provenance, f"{case_id}: no cast provenance recorded"
        assert set(cast_provenance.values()) <= SYNTHETIC_PROVENANCE, (
            f"{case_id}: unknown provenance {set(cast_provenance.values())}"
        )
        assert provenance["zeroRealPii"] is True
        for field_name in ("applicant", "carrier", "defenseFirm"):
            assert field_name in cast_provenance, f"{case_id}: {field_name} provenance missing"


def test_zero_real_pii_goes_false_when_a_cast_field_is_unvouched() -> None:
    """A flag that cannot be false is not a flag. Prove this one can.

    The engine has no channel that produces an unvouched identity today, which
    is exactly why this has to be constructed by hand: without it the assertion
    ``zeroRealPii is True`` everywhere else is indistinguishable from the
    hardcoded literal it replaced.
    """
    from dataclasses import replace

    from wc_caseload_engine.case_context import build_case_cast
    from wc_caseload_engine.lifecycle_bridge import build_timeline

    seed = parse_case_seed(
        {
            "case_id": "pii-probe",
            "rng_seed": 4242,
            "injury": {
                "type": "specific",
                "date_of_injury": "2023-01-05",
                "body_parts": [{"part": "knee", "icd10": "M23.51"}],
            },
        }
    )
    cast = build_case_cast(seed, build_timeline(seed))
    assert cast.zero_real_pii is True
    assert set(cast.provenance.values()) <= SYNTHETIC_PROVENANCE

    tainted = replace(
        cast, provenance={**cast.provenance, "applicant": "imported-real-roster"}
    )
    assert tainted.zero_real_pii is False


# ---------------------------------------------------------------------------
# ISC-74 — generation never writes outside --out
# ---------------------------------------------------------------------------


def _snapshot(root: Path) -> dict[str, tuple[int, int]]:
    """Every file under *root* as ``path -> (size, mtime_ns)``."""
    return {
        str(path.relative_to(root)): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_generation_writes_nothing_outside_the_output_directory(tmp_path: Path) -> None:
    """Redirect every write-attracting environment variable into one watched tree.

    ``HOME``, ``TMPDIR`` and the XDG cache/config/data directories are the
    places a library writes to when it writes somewhere you did not ask for —
    font caches, matplotlib configs, temp spool files. Pointing all of them at
    one sandbox turns "did anything escape?" into a single directory diff, and
    seeding sentinel files means a *modified* file fails as loudly as a new one.
    """
    sandbox = tmp_path / "sandbox"
    home = sandbox / "home"
    tmpdir = sandbox / "tmp"
    cache = sandbox / "cache"
    config = sandbox / "config"
    data = sandbox / "data"
    workdir = tmp_path / "cwd"
    for directory in (home, tmpdir, cache, config, data, workdir):
        directory.mkdir(parents=True)
        (directory / "sentinel.txt").write_text("untouched\n", encoding="utf-8")

    spec = workdir / "spec.yaml"
    spec.write_text(
        yaml.safe_dump(
            {
                "caseload_id": "scoped-load",
                "cases": [
                    {
                        "case_id": "scoped-001",
                        "rng_seed": 8181,
                        "injury": {
                            "type": "specific",
                            "date_of_injury": "2023-05-05",
                            "body_parts": [{"part": "knee", "icd10": "M23.51"}],
                        },
                        "documents": {"global_cap": 6},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    spec_snapshot = _snapshot(workdir)

    out = tmp_path / "out"
    before = _snapshot(sandbox)

    environment = {
        **os.environ,
        "HOME": str(home),
        "TMPDIR": str(tmpdir),
        "TMP": str(tmpdir),
        "TEMP": str(tmpdir),
        "XDG_CACHE_HOME": str(cache),
        "XDG_CONFIG_HOME": str(config),
        "XDG_DATA_HOME": str(data),
    }
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
        capture_output=True,
        text=True,
        check=False,
        cwd=str(workdir),
        env=environment,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]

    after = _snapshot(sandbox)
    created = sorted(set(after) - set(before))
    modified = sorted(name for name in before if name in after and after[name] != before[name])
    removed = sorted(set(before) - set(after))

    assert not created, f"generation created {len(created)} file(s) outside --out: {created[:10]}"
    assert not modified, f"generation modified {modified[:10]}"
    assert not removed, f"generation removed {removed[:10]}"

    # The working directory holds only what the test put there.
    assert _snapshot(workdir) == spec_snapshot, "generation wrote into the working directory"
    assert list(out.rglob("manifest.json")), "nothing was written to --out either"
