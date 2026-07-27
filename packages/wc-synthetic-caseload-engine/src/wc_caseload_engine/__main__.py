"""``python -m wc_caseload_engine`` — the module form of the console script.

Exists so :func:`~wc_caseload_engine.determinism.ensure_stable_hashing` has a
launcher it can re-enter. That function re-executes the interpreter with
``PYTHONHASHSEED=0``, and re-executing ``sys.argv[0]`` would only work when the
process started from the ``wc-caseload`` console script; a ``python -m`` start
would silently become a script start. Re-entering through ``-m`` resolves the
same package through the same interpreter's import system, so both invocation
styles survive the re-exec unchanged.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from wc_caseload_engine.cli import main

if __name__ == "__main__":
    main()
