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

__version__ = "0.1.0"

__all__ = ["__version__"]
