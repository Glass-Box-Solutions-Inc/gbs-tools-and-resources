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

import json
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
    synthetic_employer_name,
    synthetic_facility_name,
    synthetic_firm_name,
)
from wc_caseload_engine.name_denylist import (
    DENYLIST_PATH,
    ORGANIZATION_POOL_ATTRIBUTES,
    substrate_organization_pools,
)
from wc_caseload_engine.seeds import parse_case_seed
from wc_caseload_engine.substrate import find_substrate

pytestmark = requires_substrate

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


def _probe_seed(rng_seed: int) -> Any:
    """A minimal seed carrying no declared organization names."""
    return parse_case_seed(
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


def test_coined_organization_names_never_collide_with_the_denylist() -> None:
    """Every name the engine can coin, checked against the list once."""
    offences: list[str] = []
    for rng_seed in range(200):
        seed = _probe_seed(rng_seed)
        coined = [
            synthetic_carrier_name(seed),
            synthetic_firm_name(seed, "defense_firm"),
            synthetic_facility_name(seed, "treating"),
            *(
                synthetic_employer_name(seed, industry)
                for industry in (
                    "government",
                    "manufacturing",
                    "construction",
                    "healthcare",
                    "warehouse_logistics",
                    "retail_service",
                    "",
                )
            ),
        ]
        for name in coined:
            for hit in _hits(name):
                offences.append(f"{name!r} matches {hit!r}")
    assert not offences, offences


# ---------------------------------------------------------------------------
# ISC-73 — the substrate's organization pools, swept dynamically
# ---------------------------------------------------------------------------


def _substrate_pool_names() -> dict[str, str]:
    """``lowercased name -> pool it came from``, read live from the substrate.

    Built from the substrate module rather than transcribed, so a pool that
    grows upstream is swept without anyone remembering to update a fixture.
    Short and generic entries are dropped: ``EMPLOYERS`` (a real carrier's
    literal trading name) would fire on the word "employers" in ordinary prose,
    and a probe that cries wolf gets muted.
    """
    names: dict[str, str] = {}
    for pool, entries in substrate_organization_pools().items():
        for entry in entries:
            lowered = entry.strip().lower()
            if len(lowered) >= 12 and " " in lowered:
                names[lowered] = pool
    return names


def test_the_substrate_pool_sweep_is_loaded_and_non_trivial() -> None:
    """Guards the sweep below: an empty pool list would make it pass vacuously."""
    pools = substrate_organization_pools()
    assert set(pools) == set(ORGANIZATION_POOL_ATTRIBUTES)
    for attribute in ORGANIZATION_POOL_ATTRIBUTES:
        assert pools[attribute], f"{attribute} contributed no names"
    assert len(_substrate_pool_names()) >= 40


def test_the_substrate_pool_sweep_would_catch_a_pool_name() -> None:
    """Positive control — the sweep must fire on a name that is really in a pool."""
    pool_names = _substrate_pool_names()
    assert "kaiser permanente" in pool_names
    assert "costco wholesale" in pool_names
    assert "zenith insurance company" in pool_names
    text = "The employer of record is Kaiser Permanente."
    assert [name for name in pool_names if name in text.lower()]


def test_no_demo_value_matches_any_substrate_organization_pool(
    demo_manifests: dict[str, dict[str, Any]],
) -> None:
    """The whole point of the substitution: no pool name survives to output.

    Sweeps three surfaces at once — the manifest cast, the manifest's own JSON
    (which carries lien claimants, warnings and every recorded field), and the
    text of every text-bearing document. The pool list is built from the
    substrate module at run time, so this cannot go stale the way a hand-copied
    denylist can.
    """
    pool_names = _substrate_pool_names()
    offences: list[str] = []

    for case_id, manifest in sorted(demo_manifests.items()):
        haystacks: list[tuple[str, str]] = [
            ("manifest", json.dumps({k: v for k, v in manifest.items() if k != "_directory"}))
        ]
        for entry, path in iter_documents(manifest):
            if entry["format"] in NON_TEXT_FORMATS:
                continue
            text = extract_text(path, entry["format"])
            if text.strip():
                haystacks.append((entry["filename"], text))

        for label, haystack in haystacks:
            lowered = haystack.lower()
            for name, pool in pool_names.items():
                if name in lowered:
                    offences.append(f"{case_id}/{label}: {name!r} (substrate {pool})")

    assert not offences, f"{len(offences)} substrate-pool hit(s): {sorted(set(offences))[:20]}"


def test_every_coined_cast_avoids_every_substrate_pool() -> None:
    """Two hundred casts, checked field by field against the live pools.

    Faster and broader than the document sweep, and it fails on the cast rather
    than on a rendered artefact, so a regression names the field that leaked.
    """
    from wc_caseload_engine.case_context import build_case_cast
    from wc_caseload_engine.lifecycle_bridge import build_timeline

    pool_names = _substrate_pool_names()
    offences: list[str] = []
    for rng_seed in range(200):
        seed = _probe_seed(rng_seed)
        cast = build_case_cast(seed, build_timeline(seed))
        candidates = {
            **{key: str(value) for key, value in cast.manifest_fields().items()},
            "treatingFacility": cast.case.treating_physician.facility,
            "caseTitle": cast.case.case_title,
        }
        if cast.case.qme_physician is not None:
            candidates["qmeFacility"] = cast.case.qme_physician.facility
        for index, provider in enumerate(cast.case.prior_providers or ()):
            candidates[f"priorProvider{index}Facility"] = provider.facility

        for field_name, value in candidates.items():
            lowered = str(value).lower()
            for name, pool in pool_names.items():
                if name in lowered:
                    offences.append(
                        f"rng_seed={rng_seed} {field_name}={value!r} matches {name!r} ({pool})"
                    )
    assert not offences, f"{len(offences)} leak(s): {sorted(set(offences))[:20]}"


def test_the_employer_is_coined_and_provenance_says_so() -> None:
    """The exact release-review reproduction: rng_seed 2, no employer named."""
    from wc_caseload_engine.case_context import PROVENANCE_ENGINE, build_case_cast
    from wc_caseload_engine.lifecycle_bridge import build_timeline

    seed = parse_case_seed(
        {
            "case_id": "org-probe",
            "rng_seed": 2,
            "injury": {
                "type": "specific",
                "date_of_injury": "2023-01-05",
                "body_parts": [{"part": "lumbar_spine", "icd10": "M54.5"}],
            },
        }
    )
    cast = build_case_cast(seed, build_timeline(seed))

    pool_names = _substrate_pool_names()
    assert cast.employer_name.lower() not in pool_names, (
        f"employer {cast.employer_name!r} is a substrate pool draw"
    )
    assert not _hits(cast.employer_name)
    assert cast.provenance["employer"] == PROVENANCE_ENGINE, (
        "a pool draw must not be classified as a Faker draw — that bookkeeping "
        "error is what let a real employer inherit zeroRealPii: true"
    )
    assert cast.zero_real_pii is True


def test_a_seed_declared_denylisted_name_is_kept_but_warned_about() -> None:
    """The seed is the contract — but a real name in it must not pass silently.

    Two assertions that pull in opposite directions, which is the whole point:
    the engine must *not* override a name the seed author chose (overriding it
    would make the seed stop being the contract), and it must *not* stay quiet
    about it either. ``castProvenance`` records ``seed`` rather than ``engine``,
    so a reviewer can see whose choice it was.
    """
    from structlog.testing import capture_logs

    from wc_caseload_engine.case_context import PROVENANCE_SEED, build_case_cast
    from wc_caseload_engine.lifecycle_bridge import build_timeline

    seed = parse_case_seed(
        {
            "case_id": "seed-declared-real",
            "rng_seed": 909,
            "profile": {"employer": {"name": "Costco Wholesale"}},
            "injury": {
                "type": "specific",
                "date_of_injury": "2023-01-05",
                "body_parts": [{"part": "knee", "icd10": "M23.51"}],
            },
        }
    )
    with capture_logs() as entries:
        cast = build_case_cast(seed, build_timeline(seed))

    assert cast.employer_name == "Costco Wholesale", "the seed's own input was overridden"
    assert cast.provenance["employer"] == PROVENANCE_SEED

    warnings = [
        entry
        for entry in entries
        if entry.get("event") == "cast.seed_name_on_denylist"
        and entry.get("log_level") == "warning"
    ]
    assert warnings, f"no denylist warning was emitted; got {[e.get('event') for e in entries]}"
    assert warnings[0]["field"] == "profile.employer.name"
    assert warnings[0]["value"] == "Costco Wholesale"
    assert "costco wholesale" in warnings[0]["matched"]


def test_a_clean_seed_declared_name_produces_no_warning() -> None:
    """The warning must be a signal, not a constant — prove it can stay silent."""
    from structlog.testing import capture_logs

    from wc_caseload_engine.case_context import build_case_cast
    from wc_caseload_engine.lifecycle_bridge import build_timeline

    seed = parse_case_seed(
        {
            "case_id": "seed-declared-clean",
            "rng_seed": 909,
            "profile": {"employer": {"name": "Inland Valley Distribution"}},
            "injury": {
                "type": "specific",
                "date_of_injury": "2023-01-05",
                "body_parts": [{"part": "knee", "icd10": "M23.51"}],
            },
        }
    )
    with capture_logs() as entries:
        build_case_cast(seed, build_timeline(seed))

    assert not [e for e in entries if e.get("event") == "cast.seed_name_on_denylist"]


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


PACKAGE_SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
"""This package's own source tree — a place generation must not write either."""

BOOTSTRAP_BYTECODE = "wc_caseload_engine/__pycache__/__init__.cpython-"
"""The one file CPython writes before any line of this package can run.

``wc_caseload_engine/__init__.py`` raises ``sys.dont_write_bytecode`` on its
first executable line, which stops every later import — the rest of the
package, click, structlog and the entire substrate — from caching bytecode. Its
*own* ``.pyc`` is written by the import system while compiling that file, before
the flag exists to be set. That is an interpreter floor rather than a gap in the
guarantee, so it is named here explicitly instead of exempting a directory: any
*other* bytecode file is a real escape and fails the test.
"""


def test_generation_writes_no_bytecode_into_the_package_or_substrate_trees(
    tmp_path: Path,
) -> None:
    """``--out`` is the whole write surface, and ``__pycache__`` used to escape it.

    A fresh interpreter caches bytecode for everything it imports, and this tool
    imports a substrate that lives outside its own package. Thirteen
    ``__pycache__`` directories were appearing across the package and the
    substrate source trees on every run — writes into a read-only dependency,
    from a tool whose documented contract is that it writes only under
    ``--out``.

    Snapshotting both source trees is the only honest check: the sandboxed-HOME
    probe above cannot see these, because the source trees are neither ``HOME``
    nor ``TMPDIR`` nor the working directory.
    """
    substrate_root = find_substrate()
    assert substrate_root is not None, "probe requires the substrate on disk"

    spec = tmp_path / "spec.yaml"
    spec.write_text(
        yaml.safe_dump(
            {
                "caseload_id": "bytecode-load",
                "cases": [
                    {
                        "case_id": "bytecode-001",
                        "rng_seed": 5150,
                        "injury": {
                            "type": "specific",
                            "date_of_injury": "2023-05-05",
                            "body_parts": [{"part": "knee", "icd10": "M23.51"}],
                        },
                        "documents": {"global_cap": 5},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    before_package = _snapshot(PACKAGE_SOURCE_ROOT)
    before_substrate = _snapshot(Path(substrate_root))

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "wc_caseload_engine",
            "generate",
            "--spec",
            str(spec),
            "--out",
            str(tmp_path / "out"),
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(tmp_path),
        env={k: v for k, v in os.environ.items() if k != "PYTHONDONTWRITEBYTECODE"},
    )
    assert completed.returncode == 0, completed.stderr[-2000:]

    substrate_created = sorted(set(_snapshot(Path(substrate_root))) - set(before_substrate))
    assert not substrate_created, (
        f"generation wrote {len(substrate_created)} file(s) into the substrate source "
        f"tree: {substrate_created[:10]}"
    )

    package_created = sorted(set(_snapshot(PACKAGE_SOURCE_ROOT)) - set(before_package))
    unexpected = [name for name in package_created if BOOTSTRAP_BYTECODE not in name]
    assert not unexpected, (
        f"generation wrote {len(unexpected)} unexpected file(s) into the package source "
        f"tree: {unexpected[:10]}"
    )
