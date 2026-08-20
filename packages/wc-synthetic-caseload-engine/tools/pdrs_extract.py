#!/usr/bin/env python3
"""AJC-64 item 0b — the PDRS text derivation, executable and pinned (M5-R42(a)).

Usage::

    python tools/pdrs_extract.py --verify     # re-derive and compare (CI/default)
    python tools/pdrs_extract.py --write      # re-derive and overwrite the artifact

**Why this file exists.** The pin chain used to compare
``PDRS_2005_PDF_SHA256`` against ``meta.json``'s copy of the same constant — a
chain terminating in a string, which passes identically against a fabricated
PDF. Terminating it in bytes is necessary but not sufficient: the parity
oracles parse the *extracted text*, and "this text came from that PDF" was, in
round 1, an assertion nobody could re-run. Provenance you cannot reproduce is a
claim, not evidence.

So the derivation is one command, recorded here with its exact arguments, and
both ends of it are pinned:

    pdftotext -layout <source pdf> <output txt>

    input   src/wc_caseload_engine/data/pdrs-2005-source.pdf
            sha256 cfabf43b…f664201   (4,005,811 bytes)
    output  src/wc_caseload_engine/data/pdrs-2005-extracted-text.txt
            sha256 827d6644…f83f47b1  (335,912 bytes)

**The tool version is part of the contract**, because a layout extractor's
output is a function of its version. Verified reproducing the pinned digest
exactly under **poppler pdftotext 22.02.0**. ``--verify`` reports the version it
ran under beside any mismatch, so a digest that moves because poppler moved is
distinguishable from one that moved because the artifact did — those need
opposite responses, and a bare "digest mismatch" cannot tell them apart.

``-layout`` is not cosmetic. The five per-table parity oracles read column
positions out of this text; the default reading-order mode collapses the
columns and hashes to ``3e95899b…`` instead. The flag is pinned for that reason
rather than by habit.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
DATA = PACKAGE / "src" / "wc_caseload_engine" / "data"

SOURCE_PDF = DATA / "pdrs-2005-source.pdf"
EXTRACTED_TEXT = DATA / "pdrs-2005-extracted-text.txt"

SOURCE_PDF_SHA256 = "cfabf43b57533b90133f71aecf882c8b17a5dad3659db7aea6e810728f664201"
EXTRACTED_TEXT_SHA256 = (
    "827d66440bc9161743aa6add355c823a6d7d5913162df140f38bc871f83f47b1"
)

#: The exact invocation. Pinned as data so the test can assert the arguments
#: rather than trusting this docstring.
PDFTOTEXT_ARGS: tuple[str, ...] = ("-layout",)

#: The version this derivation was verified reproducible under.
VERIFIED_POPPLER_VERSION = "22.02.0"

SOURCE_URL = "https://www.dir.ca.gov/dwc/pdr.pdf"


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pdftotext_version() -> str:
    """The poppler version string, or "" when the binary is absent."""
    binary = shutil.which("pdftotext")
    if binary is None:
        return ""
    result = subprocess.run(
        [binary, "-v"], capture_output=True, text=True, check=False
    )
    match = re.search(r"pdftotext version ([\d.]+)", result.stdout + result.stderr)
    return match.group(1) if match else ""


def derive(destination: Path) -> str:
    """Run the pinned derivation into *destination*; return its digest."""
    binary = shutil.which("pdftotext")
    if binary is None:
        raise SystemExit("pdftotext is not on PATH; install poppler-utils")
    if not SOURCE_PDF.is_file():
        raise SystemExit(f"the source PDF is missing: {SOURCE_PDF}")
    actual = sha256_of(SOURCE_PDF)
    if actual != SOURCE_PDF_SHA256:
        raise SystemExit(
            f"the source PDF hashes {actual}, pinned {SOURCE_PDF_SHA256} — "
            "the derivation input is not the artifact this pin describes"
        )
    subprocess.run(
        [binary, *PDFTOTEXT_ARGS, str(SOURCE_PDF), str(destination)], check=True
    )
    return sha256_of(destination)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--verify", action="store_true", help="re-derive and compare")
    group.add_argument("--write", action="store_true", help="re-derive and overwrite")
    args = parser.parse_args()

    version = pdftotext_version()
    print(f"pdftotext version: {version or '<absent>'} "
          f"(pinned-verified {VERIFIED_POPPLER_VERSION})")

    if args.write:
        digest = derive(EXTRACTED_TEXT)
        print(f"wrote {EXTRACTED_TEXT} sha256 {digest}")
        return 0

    with tempfile.TemporaryDirectory() as directory:
        candidate = Path(directory) / "derived.txt"
        digest = derive(candidate)
    committed = sha256_of(EXTRACTED_TEXT)
    print(f"derived   {digest}")
    print(f"committed {committed}")
    print(f"pinned    {EXTRACTED_TEXT_SHA256}")
    if committed != EXTRACTED_TEXT_SHA256:
        print("FAIL: the committed artifact does not match its pin")
        return 1
    if digest != EXTRACTED_TEXT_SHA256:
        print(
            "FAIL: re-derivation does not reproduce the pin. If the poppler "
            f"version above is not {VERIFIED_POPPLER_VERSION}, that is the "
            "likely cause and the artifact is NOT to be re-pinned on its "
            "account — a digest that moves because the tool moved and one that "
            "moves because the source moved need opposite responses."
        )
        return 1
    print("OK: source pinned, derivation reproduces the pinned output")
    return 0


if __name__ == "__main__":
    sys.exit(main())
