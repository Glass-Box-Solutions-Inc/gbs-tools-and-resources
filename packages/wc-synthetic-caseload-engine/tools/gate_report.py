"""A pytest plugin that reports *how* a run ended, not merely that it did.

The mutation gate's whole claim is "the named guard ran and its assertion
failed". A process exit code cannot carry that claim: pytest exits non-zero for
a collection error, an import error, a usage error, a fixture explosion, an
internal error and an interrupt, and the first version of the gate certified
every one of them as a guard catching its defect. Ten registered mutants named
node IDs that did not exist; all ten scored green.

So the verdict is read off the run's own reports instead. This plugin records,
for a run that must select exactly one test:

* how many tests were collected, and their node ids;
* the outcome of each phase — setup, call, teardown — separately, because a
  fixture that blew up is not a guard that fired;
* the *type* of the call-phase exception, because ``AttributeError`` from a
  broken mutation and ``AssertionError`` from a guard are both "the test did
  not pass" and only one of them is evidence;
* pytest's own exit status.

Written to the JSON file named by ``$GATE_REPORT``. Nothing here interprets the
result — that is :mod:`mutation_gate`'s job — so this file can stay dumb enough
to trust.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest

_RESULT: dict[str, Any] = {
    "collected": 0,
    "nodeids": [],
    "phases": {},
    "call_exception": None,
    "exitstatus": None,
    "internal_error": False,
}


def pytest_collection_modifyitems(items: list[Any]) -> None:
    _RESULT["collected"] = len(items)
    _RESULT["nodeids"] = [item.nodeid for item in items]


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: Any, call: Any) -> Any:
    outcome = yield
    report = outcome.get_result()
    # Last writer wins per phase; a single-test run has exactly one of each.
    _RESULT["phases"][report.when] = report.outcome
    if report.when == "call" and call.excinfo is not None:
        _RESULT["call_exception"] = call.excinfo.type.__name__


def pytest_internalerror(excrepr: Any) -> None:
    _RESULT["internal_error"] = True


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    _RESULT["exitstatus"] = int(exitstatus)
    destination = os.environ.get("GATE_REPORT")
    if destination:
        with open(destination, "w", encoding="utf-8") as handle:
            json.dump(_RESULT, handle)
