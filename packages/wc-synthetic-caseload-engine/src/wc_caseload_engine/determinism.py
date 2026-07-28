"""Reproducibility guarantees — the leaks that break byte-identical output.

The engine's headline promise is that the same seed and the same version
produce the same caseload forever — on any machine, in any timezone, on any
day. Getting there took finding five sources of drift, none of them in this
package's own logic, all of them fixed here rather than by editing the
substrate.

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
The stamp is built from the date's ``(year, month, day)`` fields directly —
never through ``mktime``/``localtime``, which would reintroduce the zone.

**3. Random PDF ``/ID`` and creation dates.**
ReportLab stamps a wall-clock creation date and a random file id; PyMuPDF
stamps a fresh ``/ID`` when it rewrites a scanned page.
``reportlab.rl_config.invariant`` handles the first — it switches ReportLab
onto a fixed ``gmtime`` epoch, so ``/CreationDate`` carries an explicit
``+00'00'`` offset and no local time — and :func:`normalize_pdf_id` the second,
rewriting in place at identical length so every xref offset stays valid.

**4. The substrate reads the wall clock (the subtle one).**
Four substrate call sites compute *content* from ``date.today()``: the
applicant's age and years-employed in a QME report, the deponent's age, the
age line in a settlement memo, and a default hire date. ``date.today()`` is
*local*, so the same command produced different documents in Sydney and in Los
Angeles — 17 of 289 demo files drifted — and would equally have drifted from
one day to the next. :func:`pin_substrate_clock` rebinds those names to
:data:`~wc_caseload_engine.seeds.ANCHOR_DATE`.

Patching substrate module attributes is a deliberate exception to this
package's "never reach into the substrate" rule, and a narrow one: the anchor
is a process-wide *constant*, so it carries none of the shared-mutable-state
risk that keeps the letterhead constant unpatched (see ``CLAUDE.md``). The
alternative was abandoning the determinism promise.

**5. Local-offset ``Date:`` headers in ``.eml``.**
``data/email_metadata.py`` builds a naive noon datetime and calls
``dt.timestamp()``, which resolves it in the *local* zone before formatting as
UTC — so every generated email drifted by the local offset.
:func:`normalize_eml` rewrites that header from the document date at a fixed
clock time in UTC, and stamps the synthetic-data marker while it is there.

Every normalization runs *before* the manifest checksum is taken, so a marker
can never invalidate a recorded MD5.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import sys
import zipfile
from datetime import UTC, date, datetime, time
from email.utils import format_datetime
from pathlib import Path

import structlog

log = structlog.get_logger(__name__)

SYNTHETIC_MARKER = "SYNTHETIC TEST DATA — wc-synthetic-caseload-engine"
"""Stamped into PDF, DOCX and EML metadata so no reader mistakes these for real.

Deliberately metadata-only and deterministic. A visible page watermark would
have to come from the substrate's page templates, which this package does not
edit; that gap is documented in ``README.md`` rather than hacked around.
"""

SYNTHETIC_EML_HEADER = "X-Synthetic-Data"
"""RFC 5322 extension header carrying the marker on generated ``.eml`` files."""

FIXED_CLOCK = time(12, 0, 0)
"""Clock time every derived timestamp uses — noon, far from any date boundary."""

STABLE_HASH_SEED = "0"
"""``PYTHONHASHSEED`` value that disables salted string hashing entirely.

The *only* accepted value. ``1``, ``2`` and ``random`` are all valid settings
that leave string hashing salted, so each of them produces a different caseload
from the same seed; :func:`ensure_stable_hashing` re-execs on every one of them.
"""

REEXEC_GUARD_VAR = "WC_CASELOAD_HASH_PINNED"
"""Hop counter carried across the re-exec so the process can never loop.

Deliberately a *counter*, not a flag. As a flag it was a bypass: anything that
pre-set it — a wrapper script, a CI job that copied a child's environment, a
developer who read the variable name and set it — suppressed the guard while
salted hashing stayed live, and ``PYTHONHASHSEED=1`` versus ``=2`` produced two
different caseloads under a variable whose name promises the opposite. The
value now says how many re-execs have been spent, and nothing else; whether
hashing is stable is answered only by :func:`hashing_is_stable`.
"""

MAX_REEXEC_HOPS = 2
"""Re-execs allowed before :func:`ensure_stable_hashing` gives up and raises.

A healthy environment needs exactly one: the child is launched with
``PYTHONHASHSEED=0`` and settles. A second means the value did not survive —
something in the launch path is overwriting it — and the only alternatives left
are an unbounded exec loop or an error. An error is the one that can be fixed.
"""

DISABLE_REEXEC_VAR = "WC_CASELOAD_NO_REEXEC"
"""Set to any non-empty value to suppress the re-exec (debuggers, profilers)."""

REEXEC_MODULE = "wc_caseload_engine"
"""Re-executed as ``python -m wc_caseload_engine`` — see :mod:`wc_caseload_engine.__main__`."""

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


def _reexec_hops() -> int:
    """How many re-execs :data:`REEXEC_GUARD_VAR` says have already been spent.

    A value this function did not write — ``true``, ``yes``, anything a human
    set by hand — counts as one hop rather than zero. The variable was set by
    *something*, and assuming the more conservative of the two readings keeps a
    hand-set value from buying extra hops while still allowing the one honest
    re-exec that fixes the seed.
    """
    raw = os.environ.get(REEXEC_GUARD_VAR)
    if not raw:
        return 0
    try:
        return max(int(raw), 0)
    except ValueError:
        return 1


def ensure_stable_hashing() -> None:
    """Re-execute this process unless ``PYTHONHASHSEED`` is exactly ``"0"``.

    Called from the CLI entry point before any generation work. Without it,
    ``list(set(...))`` inside the substrate's content pools yields a different
    order in every process, and two runs of the same spec produce different
    documents.

    **Any** other value re-execs, including a value the caller set on purpose.
    Deferring to a pre-set value was the defect this replaced: ``PYTHONHASHSEED``
    is not a boolean, and ``1`` and ``2`` are two different salts that produce
    two different caseloads from one seed — while ``random`` is the *default*
    behaviour spelled out explicitly, which the old guard read as a deliberate
    determinism choice. Only ``0`` disables salting, so only ``0`` is accepted.

    The second release review found the same defect one level up: the *sentinel*
    was read before ``PYTHONHASHSEED`` was, so pre-setting
    :data:`REEXEC_GUARD_VAR` reinstated exactly the bypass the value check had
    just closed. Order is the whole fix — the seed is checked first, and the
    sentinel is demoted to a hop counter whose only job is bounding the loop
    (:data:`MAX_REEXEC_HOPS`). Past the cap this raises rather than exec-ing
    again: a seed that will not stick is a broken launch path, and looping
    silently is the worst of the three ways to react to it.

    :data:`DISABLE_REEXEC_VAR` still opts out for debuggers and profilers, now
    with a warning: opting out is opting out of the reproducibility guarantee,
    and that is worth one line of log output.

    Raises:
        RuntimeError: when ``PYTHONHASHSEED`` is still not ``0`` after
            :data:`MAX_REEXEC_HOPS` re-execs.
    """
    if hashing_is_stable():
        return
    if os.environ.get(DISABLE_REEXEC_VAR):
        log.warning(
            "determinism.reexec_disabled",
            hash_seed=os.environ.get("PYTHONHASHSEED", "<unset>"),
            consequence=(
                "byte-identical output is NOT guaranteed — the substrate orders "
                "content-pool strings through set(), which is salted per process"
            ),
        )
        return

    hops = _reexec_hops()
    if hops >= MAX_REEXEC_HOPS:
        raise RuntimeError(
            f"PYTHONHASHSEED is {os.environ.get('PYTHONHASHSEED', '<unset>')!r} after "
            f"{hops} re-exec(s); it must be {STABLE_HASH_SEED!r} for byte-identical "
            f"output. Something in the launch path is overwriting it — check any "
            f"wrapper that sets PYTHONHASHSEED or {REEXEC_GUARD_VAR}. Set "
            f"{DISABLE_REEXEC_VAR}=1 to run anyway without the reproducibility "
            f"guarantee."
        )

    env = dict(os.environ)
    env["PYTHONHASHSEED"] = STABLE_HASH_SEED
    env[REEXEC_GUARD_VAR] = str(hops + 1)
    # Carried through the re-exec: the child is a fresh interpreter and would
    # otherwise start writing ``__pycache__`` into the package and substrate
    # source trees, which are outside ``--out``.
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    # Always re-enter through the module form. ``sys.argv[0]`` is whatever
    # launched us — the console script in ``.venv/bin``, or ``__main__.py`` when
    # started as ``python -m`` — and re-executing *that* path is only correct in
    # the first case. ``-m wc_caseload_engine`` resolves through the same
    # interpreter's import system, so both invocation styles survive the
    # re-exec, and ``python -m`` no longer degrades into the script form.
    argv = [sys.executable, "-m", REEXEC_MODULE, *sys.argv[1:]]
    log.debug("determinism.reexec", executable=sys.executable, module=REEXEC_MODULE)
    os.execve(sys.executable, argv, env)


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

    stamp = zip_date_time(doc_date)

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


def fixed_utc_datetime(doc_date: date) -> datetime:
    """The one way this package turns a date into a timestamp.

    Always :data:`FIXED_CLOCK` on *doc_date* with an explicit UTC ``tzinfo``.
    Every timestamp the engine emits — RFC 2822 headers, PDF date strings, ZIP
    entry stamps — derives from here, so none of them can pick up the machine's
    local offset. Never build a timestamp from ``datetime.now``,
    ``time.localtime`` or ``date.timestamp()``; all three are zone-dependent.
    """
    return datetime.combine(doc_date, FIXED_CLOCK, tzinfo=UTC)


def pdf_date_string(doc_date: date) -> str:
    """A PDF ``D:YYYYMMDDHHmmSS+00'00'`` date string, explicitly UTC.

    The ``+00'00'`` suffix is written literally rather than derived from the
    platform's offset, which is what makes it reproducible.
    """
    stamp = fixed_utc_datetime(doc_date)
    return f"D:{stamp.strftime('%Y%m%d%H%M%S')}+00'00'"


def zip_date_time(doc_date: date) -> tuple[int, int, int, int, int, int]:
    """A ``zipfile`` ``date_time`` tuple built straight from the date fields.

    Deliberately *not* routed through ``time.localtime``/``time.mktime``: a ZIP
    entry stamp is naive local time by specification, so converting through the
    platform's zone is precisely the bug. Reading the fields directly makes the
    stamp mean "the document's date" on every machine.
    """
    if doc_date.year < 1980:
        return _ZIP_EPOCH
    return (
        doc_date.year,
        doc_date.month,
        doc_date.day,
        FIXED_CLOCK.hour,
        FIXED_CLOCK.minute,
        FIXED_CLOCK.second,
    )


def normalize_eml(path: Path, doc_date: date) -> bytes:
    """Rewrite an ``.eml`` header block deterministically, and mark it synthetic.

    Two edits, both confined to the headers (the body is untouched):

    * ``Date:`` is regenerated from *doc_date* at :data:`FIXED_CLOCK` UTC. The
      substrate builds this header with ``datetime(...).timestamp()``, which
      resolves a naive datetime in the *local* zone, so its output moved with
      ``TZ``.
    * :data:`SYNTHETIC_EML_HEADER` is added so the file announces itself as test
      data to anything that reads it.

    Returns the normalized bytes (already written back to *path*).
    """
    text = path.read_text(encoding="utf-8")
    separator = "\n\n"
    head, found, body = text.partition(separator)
    if not found:  # pragma: no cover - the substrate always emits a body
        head, body = text, ""

    stamp = format_datetime(fixed_utc_datetime(doc_date))
    lines = [line for line in head.split("\n") if not _is_header(line, SYNTHETIC_EML_HEADER)]
    rewritten: list[str] = []
    seen_date = False
    for line in lines:
        if _is_header(line, "Date"):
            rewritten.append(f"Date: {stamp}")
            rewritten.append(f"{SYNTHETIC_EML_HEADER}: true")
            seen_date = True
        else:
            rewritten.append(line)
    if not seen_date:  # pragma: no cover - the substrate always emits a Date
        rewritten.append(f"Date: {stamp}")
        rewritten.append(f"{SYNTHETIC_EML_HEADER}: true")

    payload = (separator.join(["\n".join(rewritten), body]) if found else "\n".join(rewritten))
    encoded = payload.encode("utf-8")
    path.write_bytes(encoded)
    return encoded


def _is_header(line: str, name: str) -> bool:
    """``True`` when *line* starts the named header (case-insensitive)."""
    return line[: len(name) + 1].lower() == f"{name.lower()}:"


def mark_docx_synthetic(path: Path) -> None:
    """Record :data:`SYNTHETIC_MARKER` in a ``.docx`` file's core properties.

    Written before :func:`normalize_docx` repacks the archive, so the marker is
    inside the bytes that get hashed. ``python-docx`` leaves ``created`` and
    ``modified`` at the template's fixed values, so this adds no wall clock.
    """
    from docx import Document

    document = Document(str(path))
    document.core_properties.comments = SYNTHETIC_MARKER
    document.save(str(path))


def ensure_invariant_pdfs() -> None:
    """Pin ReportLab to invariant output and stamp the synthetic marker.

    ``rl_config.invariant`` fixes the creation date (to a ``gmtime`` epoch, so
    no local offset) and the file id. The marker rides in through
    ``BaseDocTemplate._initArgs``, the class-level defaults every
    ``SimpleDocTemplate`` copies at construction: the substrate never passes
    ``subject`` or ``producer``, so setting the defaults reaches every document
    without touching a substrate file or a render call.
    """
    from reportlab import rl_config
    from reportlab.platypus.doctemplate import BaseDocTemplate

    rl_config.invariant = 1
    BaseDocTemplate._initArgs["subject"] = SYNTHETIC_MARKER
    BaseDocTemplate._initArgs["producer"] = SYNTHETIC_MARKER


# ---------------------------------------------------------------------------
# Substrate clock pinning
# ---------------------------------------------------------------------------


class _AnchoredDate(date):
    """A ``date`` whose :meth:`today` is the anchor instead of the wall clock."""

    __slots__ = ()
    _anchor: date = date(2026, 1, 1)

    @classmethod
    def today(cls) -> date:
        """The anchor date — identical in every timezone, on every day."""
        return cls._anchor


CLOCK_PINNED_ATTRIBUTES: tuple[tuple[str, str], ...] = (
    ("data.fake_data_generator", "date"),
    ("pdf_templates.medical.qme_ame_report", "_date"),
    ("pdf_templates.summaries.settlement_memo", "date"),
)
"""Substrate ``(module, attribute)`` pairs whose ``date.today()`` leaks the clock."""

CLOCK_PINNED_CALLABLES: tuple[tuple[str, str], ...] = (
    ("data.deposition_exchanges", "_today"),
)
"""Substrate helpers that import ``date`` *inside* the function body.

A function-local ``from datetime import date`` cannot be reached by rebinding a
module attribute, so the helper itself is replaced. ``_today`` documents itself
as "separated for testability", which is exactly this use.
"""

_CLOCK_PINNED = False


def pin_substrate_clock(anchor: date | None = None) -> bool:
    """Freeze every substrate reading of "today" at *anchor*. Idempotent.

    Args:
        anchor: the date the substrate should believe it is. Defaults to
            :data:`~wc_caseload_engine.seeds.ANCHOR_DATE`, the same "today" the
            seed schema and lifecycle use.

    Returns:
        ``True`` when the pin was applied, ``False`` when it was already in
        place or the substrate is unavailable.
    """
    global _CLOCK_PINNED
    if _CLOCK_PINNED:
        return False

    from wc_caseload_engine.seeds import ANCHOR_DATE
    from wc_caseload_engine.substrate import SubstrateUnavailableError, import_substrate

    fixed = anchor or ANCHOR_DATE
    pinned_date = type("AnchoredDate", (_AnchoredDate,), {"_anchor": fixed})

    applied: list[str] = []
    try:
        for module_name, attribute in CLOCK_PINNED_ATTRIBUTES:
            module = import_substrate(module_name)
            if isinstance(getattr(module, attribute, None), type):
                setattr(module, attribute, pinned_date)
                applied.append(f"{module_name}.{attribute}")
        for module_name, attribute in CLOCK_PINNED_CALLABLES:
            module = import_substrate(module_name)
            if callable(getattr(module, attribute, None)):
                setattr(module, attribute, lambda _fixed=fixed: _fixed)
                applied.append(f"{module_name}.{attribute}")
    except SubstrateUnavailableError:
        log.warning("determinism.clock_pin_skipped", reason="substrate unavailable")
        return False

    _CLOCK_PINNED = True
    log.debug("determinism.clock_pinned", anchor=fixed.isoformat(), sites=applied)
    return True


def ensure_deterministic_substrate() -> None:
    """Everything that must be true before the first document renders.

    Idempotent and cheap after the first call, so callers may invoke it freely
    at the top of any entry point rather than reasoning about ordering.
    """
    ensure_invariant_pdfs()
    pin_substrate_clock()


__all__ = [
    "CLOCK_PINNED_ATTRIBUTES",
    "CLOCK_PINNED_CALLABLES",
    "DISABLE_REEXEC_VAR",
    "FIXED_CLOCK",
    "MAX_REEXEC_HOPS",
    "REEXEC_GUARD_VAR",
    "REEXEC_MODULE",
    "STABLE_HASH_SEED",
    "SYNTHETIC_EML_HEADER",
    "SYNTHETIC_MARKER",
    "ensure_deterministic_substrate",
    "ensure_invariant_pdfs",
    "ensure_stable_hashing",
    "fixed_utc_datetime",
    "hashing_is_stable",
    "mark_docx_synthetic",
    "normalize_docx",
    "normalize_eml",
    "normalize_pdf_id",
    "pdf_date_string",
    "pin_substrate_clock",
    "zip_date_time",
]
