"""Reproducibility guarantees — the three leaks that break byte-identical output.

The engine's headline promise is that the same seed and the same version
produce the same caseload forever. Getting there took finding three sources of
drift, none of them in this package's own logic, all of them fixed here rather
than by editing the substrate.

**1. Salted string hashing (the widest one).**
``data/content_pools.py`` does ``items = list(set(items))`` before shuffling.
Python salts ``str.__hash__`` per process, so set iteration order — and
therefore the treatment items printed in a settlement memo — changed between
runs even with a perfectly seeded RNG. The salt cannot be changed after the
interpreter starts, so :func:`ensure_stable_hashing` re-executes the process
once with ``PYTHONHASHSEED=0``.

This fixes the *class*, not the instance: any ``set``-of-strings ordering
anywhere in the substrate becomes stable, including leaks not yet found.

**2. Wall-clock ZIP timestamps in ``.docx``.**
A ``.docx`` is a ZIP, and every entry carries the modification time at save.
The XML inside was already deterministic — only the ZIP headers drifted.
:func:`normalize_docx` repacks with timestamps derived from the document date.

**3. Random PDF ``/ID`` and creation dates.**
ReportLab stamps a wall-clock creation date and a random file id; PyMuPDF
stamps a fresh ``/ID`` when it rewrites a scanned page.
``reportlab.rl_config.invariant`` handles the first, :func:`normalize_pdf_id`
the second — rewriting in place at identical length so every xref offset stays
valid.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import sys
import zipfile
from datetime import date
from pathlib import Path

import structlog

log = structlog.get_logger(__name__)

STABLE_HASH_SEED = "0"
"""``PYTHONHASHSEED`` value that disables salted string hashing entirely."""

REEXEC_GUARD_VAR = "WC_CASELOAD_HASH_PINNED"
"""Set after re-exec so the process can never loop."""

DISABLE_REEXEC_VAR = "WC_CASELOAD_NO_REEXEC"
"""Set to any non-empty value to suppress the re-exec (debuggers, profilers)."""

# A PDF file identifier is an array of two strings, and a writer may emit either
# form for each element: a hex string <ABC...> or a literal string (raw bytes).
# PyMuPDF picks per element depending on the bytes, so matching only the hex
# form silently skipped roughly one scanned PDF in a hundred.
_PDF_STRING = rb"(?:<[0-9A-Fa-f]*>|\((?:[^()\\]|\\.)*\))"
_PDF_ID_RE = re.compile(rb"/ID\s*\[\s*" + _PDF_STRING + rb"\s*" + _PDF_STRING + rb"\s*\]")

_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)
"""ZIP cannot represent dates before 1980; used when a document predates it."""


def hashing_is_stable() -> bool:
    """``True`` when this process has salted string hashing disabled."""
    return os.environ.get("PYTHONHASHSEED") == STABLE_HASH_SEED


def ensure_stable_hashing() -> None:
    """Re-execute this process once with ``PYTHONHASHSEED=0`` if it is unset.

    Called from the CLI entry point before any generation work. Without it,
    ``list(set(...))`` inside the substrate's content pools yields a different
    order in every process, and two runs of the same spec produce different
    documents.

    Respects an explicitly-set ``PYTHONHASHSEED`` (the caller has already made
    a determinism choice) and honours :data:`DISABLE_REEXEC_VAR`.
    """
    if os.environ.get(REEXEC_GUARD_VAR):
        return
    if os.environ.get(DISABLE_REEXEC_VAR):
        log.debug("determinism.reexec_disabled")
        return
    if os.environ.get("PYTHONHASHSEED"):
        # Caller pinned it deliberately; do not override their value.
        return

    env = dict(os.environ)
    env["PYTHONHASHSEED"] = STABLE_HASH_SEED
    env[REEXEC_GUARD_VAR] = "1"
    log.debug("determinism.reexec", executable=sys.executable)
    os.execve(sys.executable, [sys.executable, *sys.argv], env)


def normalize_pdf_id(pdf_bytes: bytes, seed_value: int) -> bytes:
    """Replace a PDF trailer ``/ID`` array with a deterministic value.

    The replacement is padded with whitespace to the original array's length
    whenever it fits, so byte offsets shift as little as possible. Even when it
    cannot be padded the file stays valid: the ``/ID`` lives in the trailer,
    which follows the cross-reference table, and ``startxref`` points *back* at
    that table — so nothing any offset refers to moves.
    """
    match = _PDF_ID_RE.search(pdf_bytes)
    if match is None:
        return pdf_bytes

    # A PDF file identifier is conventionally 16 bytes, i.e. 32 hex digits —
    # the same width writers emit, so the replacement pads rather than grows.
    parts = [
        hashlib.sha256(f"{seed_value}:{index}".encode()).hexdigest()[:32].upper().encode()
        for index in (1, 2)
    ]
    replacement = b"/ID[<" + parts[0] + b"><" + parts[1] + b">]"
    shortfall = len(match.group(0)) - len(replacement)
    if shortfall > 0:
        replacement = replacement[:-1] + b" " * shortfall + b"]"

    return pdf_bytes[: match.start()] + replacement + pdf_bytes[match.end() :]


def normalize_docx(path: Path, doc_date: date) -> bytes:
    """Repack a ``.docx`` with deterministic ZIP entry timestamps.

    python-docx stamps each ZIP entry with the current time at save. Entry
    *content* is already deterministic, so repacking with a timestamp derived
    from the document's own date makes the file byte-stable while leaving the
    document itself untouched.

    Returns the normalized bytes (already written back to *path*).
    """
    with zipfile.ZipFile(path) as source:
        entries = [(info, source.read(info.filename)) for info in source.infolist()]

    stamp = (
        (doc_date.year, doc_date.month, doc_date.day, 0, 0, 0)
        if doc_date.year >= 1980
        else _ZIP_EPOCH
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as target:
        for info, payload in entries:
            replacement = zipfile.ZipInfo(info.filename, date_time=stamp)
            replacement.compress_type = info.compress_type
            replacement.external_attr = info.external_attr
            replacement.internal_attr = info.internal_attr
            replacement.create_system = info.create_system
            target.writestr(replacement, payload)

    payload = buffer.getvalue()
    path.write_bytes(payload)
    return payload


def ensure_invariant_pdfs() -> None:
    """Pin ReportLab to invariant output (fixed creation date, fixed file id)."""
    from reportlab import rl_config

    rl_config.invariant = 1


__all__ = [
    "DISABLE_REEXEC_VAR",
    "REEXEC_GUARD_VAR",
    "STABLE_HASH_SEED",
    "ensure_invariant_pdfs",
    "ensure_stable_hashing",
    "hashing_is_stable",
    "normalize_docx",
    "normalize_pdf_id",
]
