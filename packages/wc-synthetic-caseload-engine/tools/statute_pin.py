#!/usr/bin/env python3
"""AJC-64 item 0e — fetch, canonicalize and digest the pinned statutes.

Usage::

    python tools/statute_pin.py --fetch          # re-fetch every pinned section
    python tools/statute_pin.py --fetch 4664     # one section
    python tools/statute_pin.py --verify         # hash what is on disk

``--fetch`` writes ``src/wc_caseload_engine/data/statutes/lc-<section>.txt``
and prints the sha256 of each artifact. A moved digest is a **deliberate
commit**: paste the printed value into :data:`wc_caseload_engine.statutes.
STATUTE_PINS` and let a reviewer see the change, exactly the way a golden
re-record works. Nothing in the test suite fetches — a test that reached the
network would be an availability check, not a provenance one.

The extraction anchor is structural rather than a text search. leginfo renders
the section body as ``<h6><b>NNNN.</b></h6>`` followed by the ``<p>`` elements
inside one ``<font face="Times New Roman">`` block, and the enacting-history
parenthetical closes it. Anchoring on that block keeps the breadcrumb headings
(division, part, chapter, article) out of the artifact, which matters because
those headings carry their own amendment years and would otherwise sit inside
a digest that is supposed to identify the section.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import urllib.request
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE / "src"))

from wc_caseload_engine.statutes import (
    STATUTE_PINS,
    canonicalize_statute_text,
    statutes_dir,
)

USER_AGENT = "wc-synthetic-caseload-engine statute pin (AJC-64 item 0e)"


class ExtractionError(RuntimeError):
    """The page did not have the shape the extractor requires."""


def fetch(section: str, *, timeout: int = 60) -> str:
    request = urllib.request.Request(
        STATUTE_PINS[section].source_url, headers={"User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def extract_section_html(page: str, section: str) -> str:
    """The section body, as raw HTML, from one leginfo page."""
    anchor = re.search(
        r'<h6[^>]*>\s*<b>\s*' + re.escape(section) + r'\.\s*</b>\s*</h6>', page
    )
    if anchor is None:
        raise ExtractionError(
            f"section {section}: no <h6><b>{section}.</b></h6> anchor on the page"
        )
    tail = page[anchor.end() :]
    end = tail.find("</font>")
    if end < 0:
        raise ExtractionError(f"section {section}: the body block is not closed")
    return tail[:end]


def derive(section: str, page: str) -> str:
    body = canonicalize_statute_text(extract_section_html(page, section))
    if not body:
        raise ExtractionError(f"section {section}: canonicalized to nothing")
    missing = [
        marker
        for marker in STATUTE_PINS[section].required_markers
        if marker not in body
    ]
    if missing:
        raise ExtractionError(
            f"section {section}: fetched text is missing {missing} — refusing to "
            "write an artifact that does not carry the subdivisions the spec relies on"
        )
    return f"{section}. {body}\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fetch", action="store_true", help="re-fetch from leginfo")
    mode.add_argument("--verify", action="store_true", help="hash the artifacts on disk")
    parser.add_argument("sections", nargs="*", help="limit to these sections")
    args = parser.parse_args(argv)

    sections = args.sections or list(STATUTE_PINS)
    unknown = [section for section in sections if section not in STATUTE_PINS]
    if unknown:
        print(f"error: unknown sections {unknown}", file=sys.stderr)
        return 2

    statutes_dir().mkdir(parents=True, exist_ok=True)
    failures = 0
    for section in sections:
        pin = STATUTE_PINS[section]
        if args.fetch:
            try:
                payload = derive(section, fetch(section)).encode("utf-8")
            except (ExtractionError, OSError) as exc:
                print(f"FAIL    {section}: {exc}", file=sys.stderr)
                failures += 1
                continue
            pin.path.write_bytes(payload)
        else:
            if not pin.path.is_file():
                print(f"MISSING {section}: {pin.path}", file=sys.stderr)
                failures += 1
                continue
            payload = pin.path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        state = "OK  " if digest == pin.sha256 else "MOVED"
        print(f"{state}  {section:<8} {digest}  ({len(payload)} bytes)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
