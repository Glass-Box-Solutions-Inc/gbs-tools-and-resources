"""wc-synthetic-caseload-engine — seed-driven synthetic CA WC attorney case files.

Phase A (this layer) provides the deterministic, substrate-independent core:

* :mod:`wc_caseload_engine.substrate` — the single ``sys.path`` bridge to
  ``merus-test-data-generator`` (never copy substrate files).
* :mod:`wc_caseload_engine.taxonomy` — the effective 353-subtype taxonomy and
  drift detection against the Adjudica-classifier TypeScript source of record.
* :mod:`wc_caseload_engine.seeds` — the seed schema (``CaseSeed`` /
  ``CaseloadSpec``), YAML loading, deep-merged defaults, auto-derivation.
* :mod:`wc_caseload_engine.doc_controls` — the pure document-control precedence
  resolver.
* :mod:`wc_caseload_engine.cli` — the ``wc-caseload`` console script.

Phase B layers lifecycle machines, the renderer bridge, and manifests on top of
these interfaces.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import sys

# The earliest executable line in this package, and therefore the earliest point
# at which bytecode caching can be switched off. Everything imported from here
# on — the rest of this package, click, structlog, and the whole substrate —
# leaves no ``__pycache__`` behind, which is what makes "writes nothing outside
# --out" true rather than nearly true.
#
# One file is unreachable from here: this module's own ``__init__`` bytecode,
# which CPython writes while compiling this file, before the first line runs.
# That is an interpreter-level floor, not a gap in the guarantee, and the
# anti-probe names it explicitly rather than exempting a directory.
sys.dont_write_bytecode = True

__version__ = "0.6.0"

__all__ = ["__version__"]
