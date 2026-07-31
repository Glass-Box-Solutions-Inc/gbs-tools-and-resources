"""ISC-129 — the follows-the-message meta-guard, made table-driven.

Phase 2 proved three seed messages by hand: apply the edit the message names,
assert the seed then loads. Hand-written proofs cover the messages someone
remembered, which are never the ones that rot — the ``decision: denied``
suggestion that named a value outside its own enum was found by reading, not by
running, and the dead ``wc-caseload taxonomy --list`` invocation survived a
review for the same reason.

The CLI half of that class is already mechanical
(``test_every_cli_invocation_in_the_source_is_real`` in ``test_scenario_p2.py``
scans the whole package). This module makes the seed half mechanical too:

* :mod:`wc_caseload_engine.message_audit` scans ``seeds.py`` for every message
  it can put in front of an author and marks the ones that *instruct*;
* :data:`REGISTRY` pairs each instruction with a seed that trips it and the edit
  the instruction prescribes;
* the completeness pair below fails red on an instruction with no entry, and on
  an entry whose instruction no longer exists.

Writing a new actionable message therefore turns this file red until somebody
proves that following it works. That is the direction that matters, and it is
the same shape as the ISC-137 marker sweep next door.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import pytest

from wc_caseload_engine.message_audit import (
    DIRECTIVE_VERBS,
    actionable_messages,
    clauses,
    directives,
    is_actionable,
    longest_literal_run,
    normalize,
    raised_messages,
    seed_source,
    unresolved_raises,
)
from wc_caseload_engine.seeds import deep_merge, parse_case_seed

#: The shortest literal stretch a message must keep through interpolation.
#:
#: A trigger proves it hit *its* message by substring-matching this run against
#: the raised text. Too short a run matches by luck, so the well-formedness
#: check below refuses to accept one.
MIN_MATCHABLE_RUN = 16

#: Words that, placed in front of an imperative, hide it from the sweep.
#:
#: Second-person and first-person-plural openings plus politeness — the shapes a
#: reviewer actually demonstrated. Articles are **not** here, and the first draft
#: that included ``the`` proved why: it flagged "the seed speaks from the
#: dispute's point of view", where ``seed`` is a directive verb in this
#: vocabulary but a noun in that sentence. A hedge list wide enough to catch
#: English is a hedge list that cries wolf.
_HEDGES = frozenset({"you", "we", "please", "kindly", "i"})

#: Modals that can sit between the hedge and the verb ("you *should* set …").
_MODALS = frozenset(
    {"should", "must", "can", "could", "may", "might", "will", "shall", "suggest"}
)


def _hides_a_verb(clause: str) -> bool:
    """Whether *clause* buries a directive verb behind a hedge or a modal.

    Deliberately narrow — it looks for the exact evasion shape a reviewer
    demonstrated, not for English generally. A broad heuristic here would flag
    ordinary explanatory prose and be switched off within a week.
    """
    words = [word.strip("\"'`([{,:;.").casefold() for word in clause.split()]
    if len(words) < 2 or words[0] not in _HEDGES:
        return False
    # Hedges as well as modals, so "We suggest you remove …" reduces to "remove".
    rest = [word for word in words[1:] if word not in _MODALS and word not in _HEDGES]
    return bool(rest) and rest[0] in DIRECTIVE_VERBS


@dataclass(frozen=True)
class RegisteredMessage:
    """One actionable message, the seed that trips it, and the edit it prescribes.

    ``directives`` is the identity. Not the line number, which moves on every
    edit above it; not the whole message, which would churn this table every
    time somebody improves a comma. The instruction *is* the thing under test:
    reword it and the proof that following it works has to be re-run, which is
    exactly what going red here forces.
    """

    where: str
    """``Class.validator`` (or bare function) in ``seeds.py`` that raises it."""

    directives: tuple[str, ...]
    """The clauses the author is told to follow, verbatim from the source."""

    trigger: dict[str, Any]
    """Seed patch that provokes the message."""

    resolution: dict[str, Any] | Callable[[str], dict[str, Any]]
    """The edit the directives prescribe, applied on top of ``trigger``.

    A callable receives the raised message text, which is how a directive that
    names a *computed* value gets followed verbatim rather than approximately —
    the runway message names a date, and reading it back is the only way to
    prove the date it names is one the validator accepts.
    """

    drop: tuple[str, ...] = ()
    """Dotted seed paths the resolution removes — "drop it" is a real edit."""

    note: str = ""
    """Why this resolution is the one the message asked for, where not obvious."""


def _base() -> dict[str, Any]:
    """A seed that loads, for every trigger to break in exactly one way."""
    return {
        "case_id": "msg-registry",
        "rng_seed": 4200,
        "injury": {
            "type": "specific",
            "date_of_injury": "2022-04-11",
            "body_parts": [{"part": "lumbar_spine"}, {"part": "shoulder"}],
        },
        "lifecycle": {"target_stage": "medical_legal", "eval_type": "qme"},
    }


def _drop(body: dict[str, Any], path: str) -> None:
    """Remove a dotted path from *body*, if it is there."""
    head, _, tail = path.partition(".")
    if not tail:
        body.pop(head, None)
        return
    nested = body.get(head)
    if isinstance(nested, dict):
        _drop(nested, tail)


def _applied(*patches: Mapping[str, Any], drop: tuple[str, ...] = ()) -> dict[str, Any]:
    body = _base()
    for patch in patches:
        body = dict(deep_merge(body, patch))
    for path in drop:
        _drop(body, path)
    return body


def _message_from(body: Mapping[str, Any]) -> str:
    """The text ``parse_case_seed`` puts in front of an author for *body*."""
    # Deliberately broad: seeds.py raises ValueError, SeedError and
    # SeedValidationError depending on which layer caught the mistake, and the
    # registry is about the text, not the class.
    with pytest.raises(Exception) as raised:
        parse_case_seed(dict(body))
    return str(raised.value)


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------


_RUNWAY_DATE = re.compile(r"Move \S+ to (\d{4}-\d{2}-\d{2}) or earlier")


def _follow_the_runway_date(message: str) -> dict[str, Any]:
    """Take the message at its word: move the injury to the date it names.

    The alternative — picking some comfortably older date — would prove that
    moving the injury back works, which nobody doubted. It would not prove the
    boundary the message *states* is one the validator accepts, and an
    off-by-one there is precisely the ``decision: denied`` defect wearing a
    different hat.
    """
    found = _RUNWAY_DATE.search(normalize(message))
    assert found, f"the runway message stopped naming a date to move to: {message!r}"
    return {"injury": {"date_of_injury": found.group(1)}}


#: Every actionable seed message, keyed by a short name for readability.
#:
#: Hand-maintained on purpose — a machine can find the messages but only a
#: person can say what following one means. The completeness pair keeps the hand
#: and the machine in agreement.
REGISTRY: dict[str, RegisteredMessage] = {
    "repeated_body_part": RegisteredMessage(
        where="_repeated_part_message",
        directives=(
            "List each part once",
            "Use injury.body_parts[].detail to describe multiple findings in one region",
        ),
        trigger={
            "injury": {"body_parts": [{"part": "lumbar_spine"}, {"part": "lumbar_spine"}]}
        },
        resolution={
            "injury": {"body_parts": [{"part": "lumbar_spine", "detail": "L4-5 and L5-S1"}]}
        },
        note="Both clauses at once: one entry for the region, the second finding in detail.",
    ),
    "short_runway": RegisteredMessage(
        where="CaseSeed._check_runway",
        directives=("Move {} to {} or earlier, or seed a lifecycle that reaches less far",),
        trigger={"injury": {"date_of_injury": "2025-12-01"}},
        resolution=_follow_the_runway_date,
    ),
    "unknown_field": RegisteredMessage(
        where="_format_errors",
        directives=("remove it or fix the spelling",),
        trigger={"lifecycle_": {"target_stage": "discovery"}},
        resolution={},
        drop=("lifecycle_",),
        note="The typo the message is written for — a trailing underscore on 'lifecycle'.",
    ),
    "liens_without_count": RegisteredMessage(
        where="LienSpec._check_consistency",
        directives=("raise count or drop the claimants",),
        trigger={"lifecycle": {"liens": {"count": 0, "claimants": ["edd"]}}},
        resolution={"lifecycle": {"liens": {"count": 1}}},
        note="The first of the two offered edits; the second drops the claimants.",
    ),
    "unknown_modality": RegisteredMessage(
        where="DiagnosticEntry._known_modality",
        directives=("Use one of: {}",),
        trigger={"scenario": {"diagnostics": {"performed": ["ultrasound"]}}},
        resolution={"scenario": {"diagnostics": {"performed": ["mri"]}}},
    ),
    "study_both_ways": RegisteredMessage(
        where="DiagnosticsScenario._no_study_is_both",
        directives=("name it once, in whichever list is true",),
        trigger={"scenario": {"diagnostics": {"performed": ["mri"], "absent": ["mri"]}}},
        resolution={"scenario": {"diagnostics": {"absent": []}}},
    ),
    "pages_per_set_inverted": RegisteredMessage(
        where="PageRange._min_does_not_exceed_max",
        directives=("Swap the two values, or raise max to at least the min",),
        trigger={"scenario": {"discovery": {"pages_per_set": {"min": 40, "max": 12}}}},
        resolution={"scenario": {"discovery": {"pages_per_set": {"min": 12, "max": 40}}}},
    ),
    "never_treated_surgery": RegisteredMessage(
        where="ScenarioSpec._never_treated_implies_no_surgery",
        directives=(
            "Set scenario.surgery to 'none' (or drop it), or change "
            "scenario.treatment.status",
        ),
        trigger={
            "scenario": {"treatment": {"status": "never_treated"}, "surgery": "performed"}
        },
        resolution={"scenario": {"surgery": "none"}},
    ),
    "never_treated_liens": RegisteredMessage(
        where="CaseSeed._check_scenario_against_the_lifecycle",
        directives=(
            "Drop those claimants (edd, ambulance, attorney_costs and self_procured "
            "are compatible), or change the treatment status",
        ),
        trigger={
            "scenario": {"treatment": {"status": "never_treated"}},
            "lifecycle": {"liens": {"count": 2, "claimants": ["medical_provider", "edd"]}},
        },
        resolution={"lifecycle": {"liens": {"claimants": ["edd", "attorney_costs"]}}},
        note="The message names these four as compatible; the test takes it at its word.",
    ),
    "denied_by_ur_without_dispute": RegisteredMessage(
        where="CaseSeed._check_scenario_against_the_lifecycle",
        directives=(
            "Add 'lifecycle: {ur_dispute: {enabled: true, decision: upheld}}' to this "
            "seed, or use scenario.surgery: 'recommended' for a request that was never "
            "adjudicated",
        ),
        trigger={"scenario": {"surgery": "denied_by_ur"}},
        resolution={"lifecycle": {"ur_dispute": {"enabled": True, "decision": "upheld"}}},
        note="Copied verbatim from the message, which is the point of the exercise.",
    ),
    "denied_by_ur_without_decision": RegisteredMessage(
        where="CaseSeed._check_scenario_against_the_lifecycle",
        directives=(
            "Set 'lifecycle: {ur_dispute: {decision: upheld}}' so the denial stands, "
            "or use scenario.surgery: 'recommended' if the request is still pending",
        ),
        trigger={
            "scenario": {"surgery": "denied_by_ur"},
            "lifecycle": {"ur_dispute": {"enabled": True}},
        },
        resolution={"lifecycle": {"ur_dispute": {"decision": "upheld"}}},
        note="The original defect: this message used to name 'denied', which is not "
        "in the enum. Following it verbatim is now a test.",
    ),
    # --- money spine (AJC-43) ---------------------------------------------
    "money_without_wages": RegisteredMessage(
        where="ScenarioSpec._money_needs_a_wage_block",
        directives=("Add a scenario.wages block, or remove scenario.{}",),
        trigger={"scenario": {"benefits": {"td_weeks": 12}}},
        resolution={"scenario": {"wages": {"base_weekly_wage": 900}}},
        note="The first of the two offered edits; the second removes the benefits block.",
    ),
    "earnings_and_shape_knobs": RegisteredMessage(
        where="WageScenario._history_is_stated_one_way",
        directives=("Remove the listed earnings, or remove {}",),
        trigger={
            "scenario": {
                "wages": {
                    "base_weekly_wage": 900,
                    "earnings": [
                        {
                            "period_start": "2022-01-03",
                            "period_end": "2022-01-16",
                            "gross": 1800,
                        }
                    ],
                }
            }
        },
        resolution={"scenario": {"wages": {}}},
        drop=("scenario.wages.earnings",),
        note="Following the first clause: drop the listed earnings, keep the described "
        "history.",
    ),
    "earning_capacity_without_a_figure": RegisteredMessage(
        where="WageScenario._history_is_stated_one_way",
        directives=(
            "Set scenario.wages.earning_capacity_weekly, or choose a method that computes",
        ),
        trigger={"scenario": {"wages": {"method": "earning_capacity"}}},
        resolution={"scenario": {"wages": {"earning_capacity_weekly": 1500}}},
    ),
    "concurrent_without_a_second_employer": RegisteredMessage(
        where="WageScenario._history_is_stated_one_way",
        directives=(
            "Set 'concurrent: true' on the second employer's periods, or set "
            "concurrent_employment to false",
        ),
        trigger={
            "scenario": {
                "wages": {
                    "concurrent_employment": True,
                    "earnings": [
                        {
                            "period_start": "2022-01-03",
                            "period_end": "2022-01-16",
                            "gross": 1800,
                        }
                    ],
                }
            }
        },
        resolution={"scenario": {"wages": {"concurrent_employment": False}}},
        note="The second clause. The first would need a new earnings entry, which "
        "deep_merge cannot express as a patch.",
    ),
    "earnings_period_inverted": RegisteredMessage(
        where="EarningsEntry._period_is_ordered_and_overtime_fits",
        directives=("Swap the two dates, or correct whichever one is mistyped",),
        trigger={
            "scenario": {
                "wages": {
                    "earnings": [
                        {
                            "period_start": "2022-01-16",
                            "period_end": "2022-01-03",
                            "gross": 1800,
                        }
                    ]
                }
            }
        },
        resolution={
            "scenario": {
                "wages": {
                    "earnings": [
                        {
                            "period_start": "2022-01-03",
                            "period_end": "2022-01-16",
                            "gross": 1800,
                        }
                    ]
                }
            }
        },
    ),
    "overtime_exceeds_gross": RegisteredMessage(
        where="EarningsEntry._period_is_ordered_and_overtime_fits",
        directives=("Raise gross to at least the overtime, or lower the overtime",),
        trigger={
            "scenario": {
                "wages": {
                    "earnings": [
                        {
                            "period_start": "2022-01-03",
                            "period_end": "2022-01-16",
                            "gross": 400,
                            "overtime": 900,
                        }
                    ]
                }
            }
        },
        resolution={
            "scenario": {
                "wages": {
                    "earnings": [
                        {
                            "period_start": "2022-01-03",
                            "period_end": "2022-01-16",
                            "gross": 900,
                            "overtime": 900,
                        }
                    ]
                }
            }
        },
        note="Following the first clause literally: gross raised to exactly the overtime, "
        "which the message says is enough.",
    ),
    "rate_basis_bound_unpaired": RegisteredMessage(
        where="RateBasisOverride._bounds_are_ordered",
        directives=("Add {}, or remove {}",),
        trigger={
            "scenario": {
                "wages": {
                    "base_weekly_wage": 900,
                    "rate_basis": {"td_min_weekly": 900},
                }
            }
        },
        resolution={"scenario": {"wages": {"rate_basis": {"td_max_weekly": 1600}}}},
        note="The first clause. A lone bound merges against the engine's unverified "
        "default at the other end, which is how a $5,000 floor once landed under a "
        "$1,539.71 ceiling and produced a rate above the maximum.",
    ),
    "rate_basis_confirmed_without_the_numbers": RegisteredMessage(
        where="RateBasisOverride._confirmation_covers_a_whole_binding",
        directives=(
            "Supply every rate_basis figure and the authority they come from, or set "
            "counsel_confirmed to false",
        ),
        trigger={
            "scenario": {
                "wages": {
                    "base_weekly_wage": 900,
                    "rate_basis": {"counsel_confirmed": True},
                }
            }
        },
        resolution={
            "scenario": {
                "wages": {
                    "rate_basis": {
                        "td_fraction": 0.6667,
                        "td_max_weekly": 1800,
                        "td_min_weekly": 240,
                        "pd_fraction": 0.6667,
                        "pd_max_weekly": 300,
                        "pd_min_weekly": 160,
                        "authority": "verified by counsel, memo of 2026-07-01",
                    }
                }
            }
        },
        note="The first clause, which is the one worth proving: confirming the engine's "
        "unverified table without restating it is the claim this package promises it "
        "can never make, and it took five words of YAML.",
    ),
    "rate_basis_bounds_inverted": RegisteredMessage(
        where="RateBasisOverride._bounds_are_ordered",
        directives=("Swap the two values, or raise the maximum",),
        trigger={
            "scenario": {
                "wages": {
                    "base_weekly_wage": 900,
                    "rate_basis": {"td_min_weekly": 900, "td_max_weekly": 200},
                }
            }
        },
        resolution={
            "scenario": {"wages": {"rate_basis": {"td_min_weekly": 200, "td_max_weekly": 900}}}
        },
    ),
    "employment_start_after_injury": RegisteredMessage(
        where="CaseSeed._check_scenario_against_the_lifecycle",
        directives=(
            "Move employment_start to on or before the injury, or correct the injury date",
        ),
        trigger={
            "scenario": {
                "wages": {"base_weekly_wage": 900, "employment_start": "2023-01-01"}
            }
        },
        resolution={"scenario": {"wages": {"employment_start": "2021-06-01"}}},
    ),
    "earnings_after_injury": RegisteredMessage(
        where="CaseSeed._check_scenario_against_the_lifecycle",
        directives=("Remove those periods, or move injury.date_of_injury later",),
        trigger={
            "scenario": {
                "wages": {
                    "earnings": [
                        {
                            "period_start": "2023-01-03",
                            "period_end": "2023-01-16",
                            "gross": 1800,
                        }
                    ]
                }
            }
        },
        resolution={"scenario": {"wages": {}}},
        drop=("scenario.wages.earnings",),
        note="The first clause. The second would move the injury past the anchor's own "
        "runway, which a different validator would then reject.",
    ),
    "settlement_without_a_settlement": RegisteredMessage(
        where="CaseSeed._check_scenario_against_the_lifecycle",
        directives=(
            "Set 'lifecycle: {resolution: {type: c_and_r}}' (or 'stipulations'), or remove "
            "scenario.settlement",
        ),
        trigger={
            "scenario": {
                "wages": {"base_weekly_wage": 900},
                "settlement": {"gross_amount": 40000},
            },
            "injury": {"date_of_injury": "2021-06-14"},
        },
        resolution={"lifecycle": {"resolution": {"type": "c_and_r"}}},
        note="Verbatim from the message. The injury moves back in the trigger because a "
        "resolved case needs the runway a medical_legal one does not.",
    ),
    "funding_stated_twice": RegisteredMessage(
        where="SettlementScenario._funding_is_stated_one_way",
        directives=(
            "Keep funding_date for an exact date, or funding_days for an interval, and "
            "drop the other",
        ),
        trigger={
            "injury": {"date_of_injury": "2021-06-14"},
            "lifecycle": {"resolution": {"type": "c_and_r"}},
            "scenario": {
                "wages": {"base_weekly_wage": 900},
                "settlement": {
                    "approval_date": "2024-01-08",
                    "funding_date": "2024-02-01",
                    "funding_days": 30,
                },
            },
        },
        resolution={"scenario": {"settlement": {}}},
        drop=("scenario.settlement.funding_days",),
        note="Keeping funding_date and dropping the other, exactly as offered. The "
        "trigger carries approval_date because an exact funding date now requires "
        "one — without it this very test went red, which is the guard reporting that "
        "'keep funding_date' had become advice that lands on a second error.",
    ),
    "funding_date_without_approval": RegisteredMessage(
        where="SettlementScenario._funding_is_stated_one_way",
        directives=(
            "Add scenario.settlement.approval_date, or state funding_days instead and "
            "let the approval date lead it",
        ),
        trigger={
            "injury": {"date_of_injury": "2021-06-14"},
            "lifecycle": {"resolution": {"type": "c_and_r"}},
            "scenario": {
                "wages": {"base_weekly_wage": 900},
                "settlement": {"funding_date": "2024-02-01"},
            },
        },
        resolution={"scenario": {"settlement": {"approval_date": "2024-01-08"}}},
        note="The first clause. A lone funding date was measured against an approval "
        "derived from the timeline, which the seed cannot see — so it published a "
        "negative funding lag and only validate caught it.",
    ),
    "settlement_gross_with_cents": RegisteredMessage(
        where="SettlementScenario._gross_is_whole_dollars",
        directives=(
            "State scenario.settlement.gross_amount as a whole number of dollars (for "
            "example {})",
        ),
        trigger={
            "injury": {"date_of_injury": "2021-06-14"},
            "lifecycle": {"resolution": {"type": "c_and_r"}},
            "scenario": {
                "wages": {"base_weekly_wage": 900},
                "settlement": {"gross_amount": 88000.99},
            },
        },
        resolution={"scenario": {"settlement": {"gross_amount": 88000}}},
        note="The figure the message itself names, taken verbatim — the release prints "
        "whole dollars, so a ledger holding cents labels a document it contradicts.",
    ),
    "funded_before_approval": RegisteredMessage(
        where="SettlementScenario._funding_is_stated_one_way",
        directives=(
            "Move funding_date to on or after the approval, or correct the approval date",
        ),
        trigger={
            "injury": {"date_of_injury": "2021-06-14"},
            "lifecycle": {"resolution": {"type": "c_and_r"}},
            "scenario": {
                "wages": {"base_weekly_wage": 900},
                "settlement": {"approval_date": "2024-03-01", "funding_date": "2024-01-01"},
            },
        },
        resolution={"scenario": {"settlement": {"funding_date": "2024-03-15"}}},
    ),
    "every_period_is_concurrent": RegisteredMessage(
        where="WageScenario._history_is_stated_one_way",
        directives=("Set 'concurrent: false' on the primary employer's periods, or add them",),
        trigger={
            "scenario": {
                "wages": {
                    "earnings": [
                        {
                            "period_start": "2022-01-03",
                            "period_end": "2022-01-16",
                            "gross": 1800,
                            "concurrent": True,
                        }
                    ]
                }
            }
        },
        resolution={
            "scenario": {
                "wages": {
                    "earnings": [
                        {
                            "period_start": "2022-01-03",
                            "period_end": "2022-01-16",
                            "gross": 1800,
                            "concurrent": False,
                        }
                    ]
                }
            }
        },
        note="The first clause. The average is taken over the *primary* employment's "
        "weeks, so a history with no primary period divided a real gross by zero weeks "
        "and published an average weekly wage of 0.00 without a word.",
    ),
    "concurrent_coverage_mismatch": RegisteredMessage(
        where="WageScenario._history_is_stated_one_way",
        directives=(
            "Replace the concurrent periods with ones covering the primary dates, or drop "
            "them and describe the second employment with concurrent_employment instead",
        ),
        trigger={
            "scenario": {
                "wages": {
                    "earnings": [
                        {
                            "period_start": "2022-04-04",
                            "period_end": "2022-04-10",
                            "gross": 1800,
                        },
                        {
                            "period_start": "2021-01-04",
                            "period_end": "2022-04-10",
                            "gross": 52000,
                            "concurrent": True,
                        },
                    ]
                }
            }
        },
        resolution={
            "scenario": {
                "wages": {
                    "earnings": [
                        {
                            "period_start": "2022-04-04",
                            "period_end": "2022-04-10",
                            "gross": 1800,
                        },
                        {
                            "period_start": "2022-04-04",
                            "period_end": "2022-04-10",
                            "gross": 900,
                            "concurrent": True,
                        },
                    ]
                }
            }
        },
        note="The first clause: the concurrent periods replaced with ones covering the "
        "primary dates. Written verb-first because the detector reads a clause's first "
        "word — 'Match the concurrent periods' was invisible to it, the ISC-150 hole.",
    ),
    "earning_capacity_figure_without_the_method": RegisteredMessage(
        where="WageScenario._dependent_fields_have_their_enabler",
        directives=(
            "Set scenario.wages.method to 'earning_capacity', or remove "
            "earning_capacity_weekly",
        ),
        trigger={
            "scenario": {
                "wages": {"base_weekly_wage": 900, "earning_capacity_weekly": 7777}
            }
        },
        resolution={"scenario": {"wages": {"method": "earning_capacity"}}},
        note="The figure used to be accepted and discarded — the seed stated 7777 and the "
        "manifest published 996.73 under a different method.",
    ),
    "settlement_gross_below_what_a_document_can_print": RegisteredMessage(
        where="SettlementScenario._gross_is_large_enough_for_a_document_to_print",
        directives=(
            "Raise scenario.settlement.gross_amount to 21 or more, or remove "
            "scenario.settlement if this case did not settle for money",
        ),
        trigger={
            "lifecycle": {"target_stage": "resolved", "resolution": {"type": "c_and_r"}},
            "scenario": {
                "wages": {"base_weekly_wage": 900},
                "settlement": {"gross_amount": 1},
            },
        },
        resolution={"scenario": {"settlement": {"gross_amount": 88000}}},
        note="`gross_amount: 0` and `1` were accepted while the stipulated award "
        "silently skipped its reconciliation for them, printing a $27,581 award beside "
        "a published $0.00. The floor is derived from what the document must print: "
        "two whole-dollar components summing to the gross, with an award divisible by "
        "twenty so its fifteen percent fee is exact.",
    ),
    "money_on_a_fatal_claim": RegisteredMessage(
        where="CaseSeed._a_fatal_injury_has_no_disability_benefits_to_pay",
        directives=(
            "Remove the money blocks from this seed, or change injury.type to "
            "'specific' or 'cumulative_trauma'",
        ),
        trigger={
            "injury": {"type": "death"},
            "scenario": {"wages": {"base_weekly_wage": 1200}},
        },
        resolution={"injury": {"type": "specific"}},
        note="A death on 2023-01-19 derived a first temporary-disability period "
        "beginning 2023-01-22 — three days after the worker died — thirteen periods "
        "totalling $39,133.85, and two permanent-disability advances. Temporary "
        "disability replaces wages the worker would have earned and permanent "
        "disability rates a living worker's residual capacity; a fatal claim pays "
        "dependency benefits, which this layer does not model.",
    ),
    "aggregate_method_without_an_aggregate": RegisteredMessage(
        where="WageScenario._dependent_fields_have_their_enabler",
        directives=(
            "Set scenario.wages.concurrent_employment to true, or mark the second "
            "employer's periods 'concurrent: true', or choose a method that averages one "
            "employment",
        ),
        trigger={
            "scenario": {
                "wages": {"base_weekly_wage": 900, "method": "concurrent_aggregate"}
            }
        },
        resolution={"scenario": {"wages": {"concurrent_employment": True}}},
        note="The first clause. The label names a fact — earnings combined across "
        "employers — so over a single employment it asserted an aggregation that did not "
        "happen, beside a concurrentEmployment of false in the same manifest.",
    ),
    "concurrent_wage_without_concurrent_employment": RegisteredMessage(
        where="WageScenario._dependent_fields_have_their_enabler",
        directives=(
            "Set scenario.wages.concurrent_employment to true, or remove "
            "concurrent_weekly_wage",
        ),
        trigger={
            "scenario": {
                "wages": {"base_weekly_wage": 900, "concurrent_weekly_wage": 8888}
            }
        },
        resolution={"scenario": {"wages": {"concurrent_employment": True}}},
    ),
    "max_days_late_without_a_count": RegisteredMessage(
        where="BenefitsScenario._lateness_is_coherent",
        directives=(
            "Add scenario.benefits.late_payments, or drop max_days_late and let diligence "
            "decide both",
        ),
        trigger={
            "scenario": {
                "wages": {"base_weekly_wage": 900},
                "benefits": {"td_weeks": 12, "max_days_late": 62},
            }
        },
        resolution={"scenario": {"benefits": {"late_payments": 2}}},
        note="The count came from the adjuster persona otherwise, so on an attentive "
        "administrator a stated sixty-two-day delay published no lateness at all.",
    ),
    "lateness_with_nothing_paid": RegisteredMessage(
        where="BenefitsScenario._every_stated_control_can_be_honoured",
        directives=("Raise td_weeks or pd_advances above zero, or drop {}",),
        trigger={
            "scenario": {
                "wages": {"base_weekly_wage": 900},
                "benefits": {
                    "td_weeks": 0,
                    "pd_advances": 0,
                    "late_payments": 3,
                    "max_days_late": 62,
                },
            }
        },
        resolution={"scenario": {"benefits": {"td_weeks": 12}}},
        note="The first clause. The seed asked for a delay file and used to get a clean "
        "one — latePayments published as 0, with nothing anywhere saying the request "
        "had been dropped.",
    ),
    "gap_with_no_run_to_hold_it": RegisteredMessage(
        where="BenefitsScenario._every_stated_control_can_be_honoured",
        directives=("Raise td_weeks to {} or more, or drop td_gap_days",),
        trigger={
            "scenario": {
                "wages": {"base_weekly_wage": 900},
                "benefits": {"td_weeks": 0, "td_gap_days": 90},
            }
        },
        resolution={"scenario": {"benefits": {"td_weeks": 12}}},
        note="Payments issue in four-week blocks and a gap sits between two of them, so "
        "the message's threshold is the shortest run that can hold one. Followed with a "
        "value at or above it, as the message says.",
    ),
    "settlement_dated_past_the_anchor": RegisteredMessage(
        where="SettlementScenario._funding_is_stated_one_way",
        directives=("Move scenario.settlement.{} to on or before {}",),
        trigger={
            "injury": {"date_of_injury": "2021-06-14"},
            "lifecycle": {"resolution": {"type": "c_and_r"}},
            "scenario": {
                "wages": {"base_weekly_wage": 900},
                "settlement": {"approval_date": "2099-01-01", "funding_days": 30},
            },
        },
        resolution={"scenario": {"settlement": {"approval_date": "2024-03-01"}}},
        note="Every document in a case is clamped to the anchor, so a 2099 approval was "
        "an event no paper in the folder could report — and it loaded, publishing a 2099 "
        "funding date beside documents dated 2026-01-01.",
    ),
    "lateness_without_late_payments": RegisteredMessage(
        where="BenefitsScenario._lateness_is_coherent",
        directives=("Raise late_payments above zero, or drop max_days_late",),
        trigger={
            "scenario": {
                "wages": {"base_weekly_wage": 900},
                "benefits": {"late_payments": 0, "max_days_late": 30},
            }
        },
        resolution={"scenario": {"benefits": {"late_payments": 2}}},
    ),
}


REGISTERED = sorted(REGISTRY)


# ---------------------------------------------------------------------------
# The sweep can see what it claims to see
# ---------------------------------------------------------------------------


class TestTheSweepIsWellFormed:
    def test_no_raise_site_is_invisible_to_the_scan(self) -> None:
        """A message the scan cannot read is where an unproven directive hides.

        Two helpers build their text away from the ``raise`` — and both really
        do carry directives — so this is asserted rather than hoped for.
        """
        opaque = unresolved_raises(seed_source())
        assert not opaque, (
            f"raise sites whose message the registry sweep cannot see: {list(opaque)}. "
            "Build the text from string literals in a module-level helper, or the "
            "directive inside it is unguarded."
        )

    def test_the_scan_finds_messages_at_all(self) -> None:
        """Anti-vacuity: an empty scan would register nothing and pass everything."""
        assert len(raised_messages(seed_source())) > 20

    def test_the_scan_finds_actionable_messages(self) -> None:
        assert actionable_messages(seed_source())


# ---------------------------------------------------------------------------
# ISC-129 — the completeness pair
# ---------------------------------------------------------------------------


def _scanned(source: str | None = None) -> dict[tuple[str, tuple[str, ...]], Any]:
    return {
        (m.where, m.directives): m
        for m in actionable_messages(source if source is not None else seed_source())
    }


def unregistered(source: str) -> list[tuple[str, tuple[str, ...]]]:
    """Actionable messages in *source* with no entry in :data:`REGISTRY`.

    A function rather than an inline expression because the planted control runs
    the very same check against a doctored source. A control that re-implements
    the check it is validating proves only that two pieces of code agree.
    """
    registered = {(e.where, e.directives) for e in REGISTRY.values()}
    return sorted(set(_scanned(source)) - registered)


class TestTheRegistryIsComplete:
    def test_every_actionable_message_is_registered(self) -> None:
        missing = unregistered(seed_source())
        assert not missing, (
            "actionable seed messages with no registry entry:\n"
            + "\n".join(f"  {where}: {list(d)}" for where, d in missing)
            + "\n\nAdd a RegisteredMessage naming the seed that trips it and the edit "
            "the message tells the author to make. A message nothing follows is a "
            "message nobody has checked."
        )

    def test_every_registry_entry_names_a_live_message(self) -> None:
        scanned = set(_scanned())
        stale = sorted(
            (name, entry.where) for name, entry in REGISTRY.items()
            if (entry.where, entry.directives) not in scanned
        )
        assert not stale, (
            f"registry entries matching no message in seeds.py: {stale}. The message "
            "was reworded, moved or deleted — re-copy its directives from the source "
            "and re-prove the resolution, or delete the entry."
        )

    def test_every_entry_is_matchable(self) -> None:
        """A pin too short to be distinctive would match a message by accident."""
        scanned = _scanned()
        for name, entry in REGISTRY.items():
            message = scanned.get((entry.where, entry.directives))
            assert message is not None, f"{name}: no live message (see the stale check)"
            run = longest_literal_run(message.template)
            assert len(run) >= MIN_MATCHABLE_RUN, (
                f"{name}: the longest interpolation-free run of its message is "
                f"{run!r} ({len(run)} chars). Too short to prove a trigger hit this "
                "message rather than some other one."
            )


# ---------------------------------------------------------------------------
# ISC-129 — following the message resolves it
# ---------------------------------------------------------------------------


class TestFollowingEveryMessageWorks:
    @pytest.mark.parametrize("name", REGISTERED)
    def test_the_trigger_raises_the_registered_message(self, name: str) -> None:
        entry = REGISTRY[name]
        message = _scanned()[(entry.where, entry.directives)]
        raised = _message_from(_applied(entry.trigger))
        run = longest_literal_run(message.template)
        assert run in normalize(raised), (
            f"{name}: the trigger raised something else, so the proof below would be "
            f"about the wrong message.\n  expected to contain: {run!r}\n  got: {raised!r}"
        )

    @pytest.mark.parametrize("name", REGISTERED)
    def test_following_the_message_produces_a_seed_that_loads(self, name: str) -> None:
        """The whole point. Apply the edit the message names; the seed must load.

        The failure is caught and re-raised as an assertion because the useful
        report is "following *this* advice left *that* error behind", not a
        pydantic traceback: a message that sends the reader to a second error is
        the defect this registry exists to make impossible.
        """
        entry = REGISTRY[name]
        raised = _message_from(_applied(entry.trigger))
        resolution = (
            entry.resolution(raised) if callable(entry.resolution) else entry.resolution
        )
        try:
            seed = parse_case_seed(_applied(entry.trigger, resolution, drop=entry.drop))
        except Exception as still_broken:
            pytest.fail(
                f"{name}: following {list(entry.directives)} left the seed invalid.\n"
                f"  the message said: {normalize(raised)}\n"
                f"  after the edit:   {normalize(str(still_broken))}"
            )
        assert seed.case_id == "msg-registry"

    @pytest.mark.parametrize("name", REGISTERED)
    def test_the_registered_directives_are_the_ones_the_author_reads(
        self, name: str
    ) -> None:
        """The pin is the *rendered* instruction, not merely the source template.

        A directive assembled from a format string could read differently once
        interpolated — that is how ``decision: denied`` looked reasonable in
        source and was wrong on screen.
        """
        entry = REGISTRY[name]
        raised = normalize(_message_from(_applied(entry.trigger)))
        for clause in entry.directives:
            literal = longest_literal_run(clause)
            assert literal in raised, (
                f"{name}: registered directive {clause!r} does not appear in the "
                f"message the author actually sees:\n  {raised}"
            )


# ---------------------------------------------------------------------------
# The planted controls — proof the guard can fail
# ---------------------------------------------------------------------------


#: An actionable message planted into a copy of ``seeds.py``.
_PLANT_ANCHOR = '            raise ValueError("injury.ct_end must be on or after injury.ct_start")'
_PLANTED = (
    '            raise ValueError("injury.ct_end must be on or after injury.ct_start. '
    'Set injury.ct_end to a later date.")'
)


class TestThePlantedControlGoesRed:
    """Without these the completeness check could be green by never looking."""

    def test_the_completeness_check_fails_on_an_unregistered_message(self) -> None:
        """The criterion, run against a source that violates it.

        ``unregistered`` is the function
        ``test_every_actionable_message_is_registered`` asserts on, so this is
        the real check meeting a real violation — not a second implementation
        agreeing with the first.
        """
        source = seed_source()
        assert _PLANT_ANCHOR in source, "the planted control's anchor moved; update it"
        assert not unregistered(source), "the registry is already incomplete"

        planted = source.replace(_PLANT_ANCHOR, _PLANTED, 1)
        assert planted != source, "the plant did not apply; update its anchor"

        caught = unregistered(planted)
        assert caught, (
            "an unregistered actionable message passed the completeness check. The "
            "sweep is not reading raise sites, so nothing here can ever fail."
        )
        assert any(
            "Set injury.ct_end to a later date" in clause
            for _, clauses in caught
            for clause in clauses
        ), f"the check went red on something other than the planted message: {caught}"

    def test_the_message_the_control_plants_on_is_not_actionable_already(self) -> None:
        """The half of the control that makes the other half mean something."""
        assert not is_actionable("injury.ct_end must be on or after injury.ct_start")
        assert is_actionable(
            "injury.ct_end must be on or after injury.ct_start. "
            "Set injury.ct_end to a later date."
        )


class TestTheDirectiveDetector:
    @pytest.mark.parametrize(
        "text",
        [
            "Set scenario.surgery to 'none'.",
            "the count is 0 — raise count or drop the claimants",
            "A study happened or it did not. Name it once.",
            "unknown field — remove it or fix the spelling",
            "Use one of: mri, ct, xray.",
        ],
    )
    def test_it_reads_a_real_instruction(self, text: str) -> None:
        assert is_actionable(text)

    @pytest.mark.parametrize(
        "text",
        [
            "lifecycle.ur_dispute.imr requires ur_dispute.enabled: true",
            "documents.format_mix must have at least one positive weight",
            "output.formats has duplicates: pdf",
            "caseload needs at least one entry in 'cases' or an 'auto' block",
            "lifecycle.reconsideration.outcome is required when enabled; allowed: denied",
        ],
    )
    def test_it_does_not_read_a_finding_as_an_instruction(self, text: str) -> None:
        assert not is_actionable(text)

    def test_a_field_path_survives_clause_splitting(self) -> None:
        """A bare split on '.' would shred every message in this module."""
        assert directives("Set lifecycle.ur_dispute.decision to upheld.") == (
            "Set lifecycle.ur_dispute.decision to upheld",
        )

    def test_the_vocabulary_is_the_limit_and_the_limit_is_stated(self) -> None:
        """The known blind spot, executable rather than merely written down.

        Detection is a curated verb list read at the *front of a clause*, which
        leaks in two ways. Pretending otherwise would be the same dishonesty
        this module exists to stop, so both are asserted rather than described.
        """
        # 1. An unknown verb. The fix is to add it to DIRECTIVE_VERBS.
        assert "nudge" not in DIRECTIVE_VERBS
        assert not is_actionable("the value is wrong. Nudge it upwards.")
        assert is_actionable("the value is wrong. Raise it upwards.")

    @pytest.mark.parametrize(
        "evasion",
        [
            "You should set scenario.surgery to 'none'.",
            "Please set scenario.surgery to 'none'.",
            "We suggest you remove the field.",
        ],
    )
    def test_a_verb_pushed_off_the_front_of_the_clause_is_missed(
        self, evasion: str
    ) -> None:
        """The wider half of the limit, found by a reviewer after the first ship.

        The verb is read from the clause's first word, so anything in front of
        it — a pronoun, a politeness, a hedge — hides a real directive. This is
        the shape most likely to be written by accident, which is why it is
        pinned by example rather than left to the comment in ``message_audit``.

        Asserting the miss locks in a known gap, which is uncomfortable and
        correct: an undisclosed gap is worse than a disclosed one, and the
        remedy is stated in the module and in the assertion below — seed
        directives are written imperative, verb first.
        """
        assert not is_actionable(evasion), (
            "the leading-pronoun hole has been closed; delete this disclosure and "
            "re-run the registry, because more messages are now actionable"
        )

    def test_the_same_instruction_verb_first_is_caught(self) -> None:
        """The other side of the pin: the miss is about shape, not content."""
        assert is_actionable("Set scenario.surgery to 'none'.")
        assert is_actionable("Remove the field.")

    def test_no_shipped_message_falls_into_the_hole(self) -> None:
        """The remedy, enforced on the messages that exist rather than advised.

        The blind spot only matters if a real message lands in it. None does,
        and this keeps it that way: a seed message written "You should set …"
        trips here even though the sweep cannot see it as a directive. That is
        the disclosure earning its keep instead of merely apologising.
        """
        offenders = [
            f"{message.where}: {clause}"
            for message in raised_messages(seed_source())
            for clause in clauses(message.template)
            if _hides_a_verb(clause)
        ]
        assert not offenders, (
            "seed messages whose clause opens with a pronoun or politeness in front "
            "of an imperative, where the sweep cannot see the directive:\n  "
            + "\n  ".join(offenders)
            + "\nRewrite it verb-first."
        )


class TestTheRegistryTableIsWellFormed:
    def test_every_entry_names_a_verb_the_vocabulary_knows(self) -> None:
        for name, entry in REGISTRY.items():
            for clause in entry.directives:
                verb = clause.split(" ", 1)[0].strip("\"'`([{").casefold()
                assert verb in DIRECTIVE_VERBS, (
                    f"{name}: directive {clause!r} opens with {verb!r}, which the "
                    "sweep does not recognise — the entry cannot have come from it"
                )

    def test_no_two_entries_claim_the_same_message(self) -> None:
        seen: dict[tuple[str, tuple[str, ...]], str] = {}
        for name, entry in REGISTRY.items():
            key = (entry.where, entry.directives)
            assert key not in seen, f"{name} duplicates {seen[key]}"
            seen[key] = name
