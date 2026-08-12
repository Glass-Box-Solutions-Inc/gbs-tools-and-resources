"""AJC-62 (M3) — the contention-loop topology gates (R43, mapped by R69).

R77 step 4 opens this module with the two response-semantics gates whose
production surface lands with the disposition remodel: the R37 revision-kind
predicates and the exact changed/unchanged percentage-row metadata. The loop
topology gates (decision table, branching, truncation, caps, explicit
composition, non-recursion, planner integration) land here with their
producers at steps 5-6; nothing in this module may be weakened when they do.

Every guard collects as exactly one non-parametrized pytest item (R74/R75
mutation discipline): fixtures vary inside the test body, never through
``pytest.mark.parametrize``.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import datetime as dt
import random
from fractions import Fraction
from functools import cache
from itertools import pairwise
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

from wc_caseload_engine import medical_assertions as assertion_module
from wc_caseload_engine.medical_assertions import (
    ADVERSE_CONTEST_PATH_WEIGHTS,
    COMPLETION_PATH_WEIGHTS,
    MAX_ADVOCACY_LETTERS_PER_CASE,
    MAX_BOUND_CONTENTION_DOCUMENTS_PER_CASE,
    MAX_CONTENTION_CHAINS_PER_CASE,
    MAX_CONTENTIONS_PER_LOOP_DOCUMENT,
    MAX_OBJECTIONS_PER_CASE,
    MAX_QME_AME_DEPOSITIONS_PER_CASE,
    MAX_SUPPLEMENTAL_REPORTS_PER_CASE,
    MAX_SUPPLEMENTAL_REQUESTS_PER_CASE,
    ApportionmentAssertion,
    AssertionTrace,
    AssertionValidationContext,
    AssertionWorldProjection,
    Contention,
    MedicalAssertionError,
    MedicalAssertionLedger,
    MedicalAssertionPlan,
    MedicalOpinion,
    ProjectedCondition,
    ProjectedPriorClaim,
    derive_medical_assertion_plan,
    validate_medical_assertions,
)
from wc_caseload_engine.medical_history import derive_medical_history
from wc_caseload_engine.medical_story import (
    ADVOCACY_LETTER_SURFACES,
    INITIAL_MEDLEGAL_SURFACES,
    PSYCH_MEDLEGAL_SURFACES,
    PTP_CAUSATION_SURFACES,
    SUPPLEMENTAL_MEDLEGAL_SURFACES,
)
from wc_caseload_engine.seeds import (
    ContentionDocumentEntry,
    SeedValidationError,
    parse_caseload_spec,
)


def _context(**overrides: Any) -> AssertionValidationContext:
    values: dict[str, Any] = {
        "date_of_injury": dt.date(2022, 4, 11),
        "anchor_date": dt.date(2026, 1, 1),
        "current_body_parts": ("lumbar_spine", "shoulder"),
        "target_stage": "medical_legal",
        "claim_response": "accepted",
        "eval_type": "qme",
    }
    values.update(overrides)
    return AssertionValidationContext(**values)


def _world() -> AssertionWorldProjection:
    return AssertionWorldProjection(
        conditions=(
            ProjectedCondition(
                id="cond-01",
                key="seeded",
                label="degenerative lumbar disease",
                causal_ground_truth="nonindustrial",
                onset=dt.date(2015, 6, 1),
                body_system="musculoskeletal",
                body_part="lumbar_spine",
                apportionment_targets=("lumbar_spine",),
                wholly_unrelated=False,
                severity="moderate",
                trajectory="stable",
                symptomatic_before_doi=True,
                surfaces_in_file=True,
            ),
        ),
        prior_claims=(
            ProjectedPriorClaim(
                id="prior-01",
                date_of_injury=dt.date(2015, 1, 5),
                body_parts=("lumbar_spine",),
                resolution_type="stipulated_award",
                overlaps_current=True,
                award=None,
            ),
        ),
    )


def _contention(contention_id: str = "ctn-01", **overrides: Any) -> Contention:
    values: dict[str, Any] = {
        "id": contention_id,
        "claim_type": "industrial_causation",
        "party": "applicant",
        "position": "affirm",
        "target_condition_id": "cond-01",
        "rationale": "the lumbar condition arose from the industrial injury",
        "quality": "supported",
    }
    values.update(overrides)
    return Contention(**values)


def _base_opinion(**overrides: Any) -> MedicalOpinion:
    values: dict[str, Any] = {
        "id": "opn-01",
        "author_role": "qme",
        "report_stage": "final",
        "report_date": dt.date(2023, 6, 1),
        "apportionment_state": "determined",
        "determination_kind": "allocated",
        "determination_rationale": "the split follows the imaging severity",
        "examination_performed": True,
        "reviewed_condition_ids": ("cond-01",),
        "endorses_contention_ids": ("ctn-01",),
        "aoe_coe_finding": "industrial",
        "aoe_coe_rationale": "mechanism and course support industrial causation",
        "rationale": "reviewed the record and examined the applicant",
        "quality": "supported",
    }
    values.update(overrides)
    return MedicalOpinion(**values)


def _response_opinion(**overrides: Any) -> MedicalOpinion:
    values: dict[str, Any] = {
        "id": "opn-02",
        "author_role": "qme",
        "report_stage": "final",
        "report_date": dt.date(2023, 11, 1),
        "apportionment_state": "determined",
        "determination_kind": "allocated",
        "determination_rationale": "the split stands as previously stated",
        "examination_performed": False,
        "event_kind": "supplemental_report",
        "revision_kind": "unchanged_additional_reasoning",
        "responds_to_opinion_id": "opn-01",
        "reviewed_condition_ids": ("cond-01",),
        "endorses_contention_ids": ("ctn-01",),
        "aoe_coe_finding": "industrial",
        "aoe_coe_rationale": "mechanism and course support industrial causation",
        "rationale": "the written conclusions stand with additional reasoning",
        "quality": "supported",
    }
    values.update(overrides)
    return MedicalOpinion(**values)


def _row(
    assertion_id: str, opinion_id: str, nonindustrial: int, **overrides: Any
) -> ApportionmentAssertion:
    values: dict[str, Any] = {
        "id": assertion_id,
        "opinion_id": opinion_id,
        "body_part": "lumbar_spine",
        "industrial_percent": 100 - nonindustrial,
        "nonindustrial_percent": nonindustrial,
        "basis_kinds": ("preexisting_degenerative_pathology",),
        "condition_ids": ("cond-01",),
        "description": "chronic lumbar disability limiting weight-bearing",
        "disability_causation_stated": True,
        "reasonable_medical_probability": True,
        "causal_rationale": "degenerative pathology contributes to the disability",
        "percentage_rationale": "the share reflects the imaging severity",
        "quality": "supported",
    }
    values.update(overrides)
    return ApportionmentAssertion(**values)


def _problems(
    opinions: tuple[MedicalOpinion, ...],
    assertions: tuple[ApportionmentAssertion, ...] = (),
) -> tuple[str, ...]:
    ledger = MedicalAssertionLedger(
        contentions=(_contention(),),
        medical_opinions=opinions,
        apportionment_assertions=assertions,
    )
    return validate_medical_assertions(_context(), _world(), ledger)


def test_revision_kind_predicates_accept_and_reject_exact_field_changes() -> None:
    """R43's revision-taxonomy gate (R37, enforced at R77 step 4): each of the
    five kinds permits and forbids exactly its stated field changes, the
    supersession rule follows the kind, and the combined kind is a COMPLETE
    conjunction — one changed family alone is rejected in both directions."""
    base = _base_opinion()
    base_row = _row("app-01", "opn-01", 20)

    # unchanged_additional_reasoning: nothing changes, supersedes nothing —
    # accepted exactly as constructed.
    unchanged = _response_opinion()
    accepted = _problems((base, unchanged), (base_row, _row("app-02", "opn-02", 20)))
    assert accepted == ()

    # …but a causation-family change under the no-change kind is rejected —
    # here a disposition result moves (the endorsement is dropped).
    moved_disposition = _response_opinion(endorses_contention_ids=())
    problems = _problems((base, moved_disposition), (base_row, _row("app-02", "opn-02", 20)))
    assert (
        "medical opinion 'opn-02' has revision_kind "
        "'unchanged_additional_reasoning' but changes a causation-family "
        "result relative to predecessor 'opn-01'; AOE/COE, psych "
        "classification and every disposition result must remain the same "
        "under this kind"
    ) in problems

    # …an apportionment-family change under the no-change kind is rejected —
    # here the percentage moves.
    moved_percentage = _response_opinion()
    problems = _problems(
        (base, moved_percentage),
        (
            base_row,
            _row(
                "app-02",
                "opn-02",
                30,
                revised_from_percent=20,
                revision_rationale="the share moved with the new imaging",
            ),
        ),
    )
    assert any(
        problem.startswith(
            "medical opinion 'opn-02' has revision_kind "
            "'unchanged_additional_reasoning' but changes an "
            "apportionment-family result"
        )
        for problem in problems
    )

    # …and claiming supersession without a revision is rejected.
    superseding_unchanged = _response_opinion(supersedes_opinion_id="opn-01")
    problems = _problems(
        (base, superseding_unchanged), (base_row, _row("app-02", "opn-02", 20))
    )
    assert (
        "medical opinion 'opn-02' has revision_kind "
        "'unchanged_additional_reasoning' but sets supersedes_opinion_id; a "
        "response that changes no result supersedes nothing"
    ) in problems

    # new_records_no_change: accepted only when the reviewed-record union is
    # a strict superset and no result moves.
    new_records = _response_opinion(
        revision_kind="new_records_no_change",
        reviewed_condition_ids=("cond-01",),
        reviewed_prior_claim_ids=(),
    )
    problems = _problems((base, new_records), (base_row, _row("app-02", "opn-02", 20)))
    assert (
        "medical opinion 'opn-02' has revision_kind 'new_records_no_change' "
        "but its reviewed-record union is not a strict superset of "
        "predecessor 'opn-01''s; acknowledging new records is what this kind "
        "states"
    ) in problems
    base_narrow = _base_opinion(reviewed_condition_ids=("cond-01",))
    grew = _response_opinion(
        revision_kind="new_records_no_change",
        reviewed_condition_ids=("cond-01",),
        reviewed_prior_claim_ids=("prior-01",),
    )
    accepted = _problems(
        (base_narrow, grew), (base_row, _row("app-02", "opn-02", 20))
    )
    assert accepted == ()

    # revised_causation: requires a causation change, supersession of the
    # predecessor, and NO apportionment change.
    revised_causation = _response_opinion(
        revision_kind="revised_causation",
        supersedes_opinion_id="opn-01",
        aoe_coe_finding="nonindustrial",
        aoe_coe_rationale="the record now shows a nonindustrial mechanism",
        endorses_contention_ids=(),
        rejects_contention_ids=("ctn-01",),
        revision_rationale="the causation conclusion is revised",
    )
    accepted = _problems(
        (base, revised_causation), (base_row, _row("app-02", "opn-02", 20))
    )
    assert accepted == ()
    no_causation_change = _response_opinion(
        revision_kind="revised_causation",
        supersedes_opinion_id="opn-01",
        revision_rationale="claims revision while changing nothing",
    )
    problems = _problems(
        (base, no_causation_change), (base_row, _row("app-02", "opn-02", 20))
    )
    assert (
        "medical opinion 'opn-02' has revision_kind 'revised_causation' but "
        "changes no causation-family result relative to predecessor 'opn-01'"
    ) in problems
    causation_plus_percentage = _response_opinion(
        revision_kind="revised_causation",
        supersedes_opinion_id="opn-01",
        aoe_coe_finding="nonindustrial",
        revision_rationale="the causation conclusion is revised",
    )
    problems = _problems(
        (base, causation_plus_percentage),
        (
            base_row,
            _row(
                "app-02",
                "opn-02",
                30,
                revised_from_percent=20,
                revision_rationale="the share moved too",
            ),
        ),
    )
    assert (
        "medical opinion 'opn-02' has revision_kind 'revised_causation' but "
        "also changes an apportionment-family result relative to predecessor "
        "'opn-01'; use 'revised_causation_and_apportionment'"
    ) in problems
    missing_supersession = _response_opinion(
        revision_kind="revised_causation",
        aoe_coe_finding="nonindustrial",
        revision_rationale="the causation conclusion is revised",
    )
    problems = _problems(
        (base, missing_supersession), (base_row, _row("app-02", "opn-02", 20))
    )
    assert (
        "medical opinion 'opn-02' has revision_kind 'revised_causation' but "
        "supersedes_opinion_id is not its immediate predecessor 'opn-01'; a "
        "revising response supersedes exactly the report it revises"
    ) in problems

    # revised_apportionment: requires an apportionment change and NO
    # causation change.
    revised_apportionment = _response_opinion(
        revision_kind="revised_apportionment",
        supersedes_opinion_id="opn-01",
        revision_rationale="the share follows the new imaging",
    )
    accepted = _problems(
        (base, revised_apportionment),
        (
            base_row,
            _row(
                "app-02",
                "opn-02",
                30,
                revised_from_percent=20,
                revision_rationale="the share follows the new imaging",
            ),
        ),
    )
    assert accepted == ()
    no_apportionment_change = _response_opinion(
        revision_kind="revised_apportionment",
        supersedes_opinion_id="opn-01",
        revision_rationale="claims a revision while changing nothing",
    )
    problems = _problems(
        (base, no_apportionment_change), (base_row, _row("app-02", "opn-02", 20))
    )
    assert (
        "medical opinion 'opn-02' has revision_kind 'revised_apportionment' "
        "but changes no apportionment-family result relative to predecessor "
        "'opn-01'"
    ) in problems
    apportionment_plus_causation = _response_opinion(
        revision_kind="revised_apportionment",
        supersedes_opinion_id="opn-01",
        aoe_coe_finding="nonindustrial",
        revision_rationale="the share follows the new imaging",
    )
    problems = _problems(
        (base, apportionment_plus_causation),
        (
            base_row,
            _row(
                "app-02",
                "opn-02",
                30,
                revised_from_percent=20,
                revision_rationale="the share follows the new imaging",
            ),
        ),
    )
    assert (
        "medical opinion 'opn-02' has revision_kind 'revised_apportionment' "
        "but also changes a causation-family result relative to predecessor "
        "'opn-01'; use 'revised_causation_and_apportionment'"
    ) in problems

    # revised_causation_and_apportionment: the COMPLETE conjunction — both
    # families must actually change; one alone is rejected in each direction.
    combined = _response_opinion(
        revision_kind="revised_causation_and_apportionment",
        supersedes_opinion_id="opn-01",
        aoe_coe_finding="nonindustrial",
        revision_rationale="both conclusions are revised",
    )
    accepted = _problems(
        (base, combined),
        (
            base_row,
            _row(
                "app-02",
                "opn-02",
                30,
                revised_from_percent=20,
                revision_rationale="both conclusions are revised",
            ),
        ),
    )
    assert accepted == ()
    combined_missing_apportionment = _response_opinion(
        revision_kind="revised_causation_and_apportionment",
        supersedes_opinion_id="opn-01",
        aoe_coe_finding="nonindustrial",
        revision_rationale="only causation actually moved",
    )
    problems = _problems(
        (base, combined_missing_apportionment),
        (base_row, _row("app-02", "opn-02", 20)),
    )
    assert (
        "medical opinion 'opn-02' has revision_kind "
        "'revised_causation_and_apportionment' but changes no "
        "apportionment-family result relative to predecessor 'opn-01'"
    ) in problems
    combined_missing_causation = _response_opinion(
        revision_kind="revised_causation_and_apportionment",
        supersedes_opinion_id="opn-01",
        revision_rationale="only the share actually moved",
    )
    problems = _problems(
        (base, combined_missing_causation),
        (
            base_row,
            _row(
                "app-02",
                "opn-02",
                30,
                revised_from_percent=20,
                revision_rationale="only the share actually moved",
            ),
        ),
    )
    assert (
        "medical opinion 'opn-02' has revision_kind "
        "'revised_causation_and_apportionment' but changes no "
        "causation-family result relative to predecessor 'opn-01'"
    ) in problems


def test_changed_and_unchanged_percentage_rows_carry_exact_revision_metadata() -> None:
    """R43's percentage-revision gate (R37, R77 step 4): on an allocated
    predecessor, a changed row carries the exact predecessor percentage and a
    reason; an unchanged row does not claim revision; a row on a body part
    the predecessor never allocated revises nothing."""
    base = _base_opinion()
    base_row = _row("app-01", "opn-01", 20)

    def revising(**row_overrides: Any) -> tuple[str, ...]:
        response = _response_opinion(
            revision_kind="revised_apportionment",
            supersedes_opinion_id="opn-01",
            revision_rationale="the share follows the new imaging",
        )
        return _problems(
            (base, response),
            (base_row, _row("app-02", "opn-02", 30, **row_overrides)),
        )

    # The exact compliant changed row.
    assert (
        revising(
            revised_from_percent=20,
            revision_rationale="the share follows the new imaging",
        )
        == ()
    )

    # A changed row whose revised_from_percent is not the predecessor's exact
    # nonindustrial percentage.
    problems = revising(
        revised_from_percent=15,
        revision_rationale="the share follows the new imaging",
    )
    assert (
        "apportionment assertion 'app-02' changes body part 'lumbar_spine' "
        "from predecessor 'opn-01''s nonindustrial 20% but "
        "revised_from_percent is 15; a changed row carries the exact "
        "predecessor percentage"
    ) in problems

    # A changed row that claims no prior percentage at all.
    problems = revising(revision_rationale="the share follows the new imaging")
    assert (
        "apportionment assertion 'app-02' changes body part 'lumbar_spine' "
        "from predecessor 'opn-01''s nonindustrial 20% but "
        "revised_from_percent is None; a changed row carries the exact "
        "predecessor percentage"
    ) in problems

    # A changed row without a stated reason.
    problems = revising(revised_from_percent=20, revision_rationale=None)
    assert (
        "apportionment assertion 'app-02' changes body part 'lumbar_spine' "
        "from predecessor 'opn-01' without a revision_rationale; a changed "
        "percentage states its reason"
    ) in problems

    # An unchanged row claiming revision.
    unchanged_claiming = _response_opinion()
    problems = _problems(
        (base, unchanged_claiming),
        (
            base_row,
            _row(
                "app-02",
                "opn-02",
                20,
                revised_from_percent=20,
                revision_rationale="claims a revision that never happened",
            ),
        ),
    )
    assert (
        "apportionment assertion 'app-02' keeps predecessor 'opn-01''s "
        "nonindustrial 20% for body part 'lumbar_spine' but sets "
        "revised_from_percent; an unchanged row does not claim revision"
    ) in problems

    # A row on a body part the predecessor never allocated cannot claim a
    # revision source there.
    new_part = _response_opinion(
        revision_kind="revised_apportionment",
        supersedes_opinion_id="opn-01",
        revision_rationale="a fresh shoulder allocation",
    )
    problems = _problems(
        (base, new_part),
        (
            base_row,
            _row("app-02", "opn-02", 20),
            _row(
                "app-03",
                "opn-02",
                10,
                body_part="shoulder",
                condition_ids=(),
                basis_kinds=("nonindustrial_medical_condition",),
                revised_from_percent=10,
                revision_rationale="claims a shoulder revision from nothing",
            ),
        ),
    )
    assert (
        "apportionment assertion 'app-03' sets revised_from_percent but "
        "predecessor 'opn-01' allocated no percentage for body part "
        "'shoulder'"
    ) in problems


# ---------------------------------------------------------------------------
# R77 step 5 — the R67 loop matrix, forced-stream helpers, and derivation
# ---------------------------------------------------------------------------

_FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "medical_story_loop_matrix.yaml"

#: R29's complete disposition x party decision table, restated independently
#: (never imported from production): (party, disposition) -> (actor, class).
_R29_TABLE_LITERAL: dict[tuple[str, str], tuple[str, str]] = {
    ("applicant", "adopted"): ("defense", "determined_adverse"),
    ("applicant", "concurred"): ("defense", "determined_adverse"),
    ("applicant", "rejected"): ("applicant", "determined_adverse"),
    ("applicant", "deferred"): ("applicant", "completion"),
    ("applicant", "unaddressed"): ("applicant", "completion"),
    ("defense", "adopted"): ("applicant", "determined_adverse"),
    ("defense", "concurred"): ("applicant", "determined_adverse"),
    ("defense", "rejected"): ("defense", "determined_adverse"),
    ("defense", "deferred"): ("defense", "completion"),
    ("defense", "unaddressed"): ("defense", "completion"),
}

#: The ten R67 fixture rows in file order: (case_id, party, disposition).
_MATRIX_ROWS: tuple[tuple[str, str, str], ...] = tuple(
    (f"loop-{party}-{label}", party, disposition)
    for party in ("applicant", "defense")
    for label, disposition in (
        ("adopted", "adopted"),
        ("concurred", "concurred"),
        ("rejected", "rejected"),
        ("deferred", "deferred"),
        ("unaddressed", "unaddressed"),
    )
)


@cache
def _fixture_payload_text() -> str:
    return _FIXTURE_PATH.read_text(encoding="utf-8")


def _fixture_payload() -> dict[str, Any]:
    return yaml.safe_load(_fixture_payload_text())


@cache
def _matrix_seeds() -> dict[str, Any]:
    spec = parse_caseload_spec(_fixture_payload())
    return {case.case_id: case for case in spec.cases}


def _patched_seed(case_id: str, mutate: Any) -> Any:
    """One fixture case re-parsed after *mutate* edits its raw payload."""
    payload = _fixture_payload()
    case = next(c for c in payload["cases"] if c["case_id"] == case_id)
    mutate(case)
    spec = parse_caseload_spec(payload)
    return next(c for c in spec.cases if c.case_id == case_id)


def _derive(seed: Any) -> tuple[Any, AssertionTrace, MedicalAssertionPlan]:
    history = derive_medical_history(seed)
    trace = AssertionTrace()
    plan = derive_medical_assertion_plan(seed, history, trace=trace)
    return history, trace, plan


class _ForcedStream(random.Random):
    """One entity-private stream whose next result the test dictates.

    R67 sanctions replacing an entity-private rng result with a deterministic
    test choice; production constants are never altered — a forced uniform is
    still evaluated against the production weights.
    """

    def __init__(self, *, uniform: float | None = None, endpoint: str | None = None) -> None:
        super().__init__(0)
        self._uniform = uniform
        self._endpoint = endpoint

    def random(self) -> float:
        if self._uniform is None:
            return super().random()
        return self._uniform

    def randint(self, lower: int, upper: int) -> int:
        if self._endpoint == "lower":
            return lower
        if self._endpoint == "upper":
            return upper
        return super().randint(lower, upper)


def _fire(*_args: Any) -> _ForcedStream:
    return _ForcedStream(uniform=0.0)


def _miss(*_args: Any) -> _ForcedStream:
    return _ForcedStream(uniform=1.0)


def _upper(*_args: Any) -> _ForcedStream:
    return _ForcedStream(endpoint="upper")


def _selecting_uniform(table: tuple[tuple[Any, Fraction], ...], target: Any) -> float:
    """The uniform draw that selects *target* under the production weights."""
    cumulative = 0.0
    for name, weight in table:
        share = float(weight)
        if name == target:
            return cumulative + share / 2.0
        cumulative += share
    raise AssertionError(f"{target!r} is not a member of the weight table")


def _force_path(adverse: str | None, completion: str | None = None) -> Any:
    """A ``contest-path`` maker selecting the named literal per class."""

    def maker(_seed: Any, _family: str, key: Any) -> _ForcedStream:
        x_key = key[2]
        actor, disposition_class = x_key[3], x_key[4]
        if disposition_class == "determined_adverse":
            assert adverse is not None, "an adverse opportunity fired unexpectedly"
            table = ADVERSE_CONTEST_PATH_WEIGHTS.value[actor]
            return _ForcedStream(uniform=_selecting_uniform(table, adverse))
        assert completion is not None, "a completion opportunity fired unexpectedly"
        table = COMPLETION_PATH_WEIGHTS.value[actor]
        return _ForcedStream(uniform=_selecting_uniform(table, completion))

    return maker


def _route_story_streams(
    monkeypatch: pytest.MonkeyPatch,
    forced: dict[str, Any],
    recorded: list[tuple[str, Any]] | None = None,
) -> None:
    """Route the wrapped module attribute: record every construction, force
    exactly the named families, and pass everything else to production."""
    original = assertion_module._medical_story_rng

    def router(seed: Any, family: str, semantic_key: Any) -> Any:
        if recorded is not None:
            recorded.append((family, semantic_key))
        maker = forced.get(family)
        if maker is None:
            return original(seed, family, semantic_key)
        return maker(seed, family, semantic_key)

    monkeypatch.setattr(assertion_module, "_medical_story_rng", router)


def _contest_world(adverse: str | None, completion: str | None = None) -> dict[str, Any]:
    """The standard forced world: every contest opportunity fires, advocacy
    stays quiet, and the path draw selects the named literal."""
    return {
        "advocacy-incidence": _miss,
        "applicant-contest-incidence": _fire,
        "completion-incidence": _fire,
        "defense-contest-incidence": _fire,
        "contest-path": _force_path(adverse, completion),
    }


def _sampled_contest_documents(plan: MedicalAssertionPlan) -> list[Any]:
    """The sampled loop communications and realizations, in composition
    order, excluding base-report realizations and advocacy."""
    return [
        binding
        for binding in plan.contention_documents
        if binding.source == "sampled" and binding.document_kind != "advocacy"
    ]


_INCIDENCE_FAMILIES = frozenset(
    {
        "applicant-contest-incidence",
        "completion-incidence",
        "defense-contest-incidence",
    }
)


# ---------------------------------------------------------------------------
# R43 loop-absent gate
# ---------------------------------------------------------------------------


def test_contention_loop_is_absent_without_history_or_assertions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R43's absence gate (R25): without ``scenario.medical_assertions`` the
    plan is empty and NO medical-story stream is constructed — the absent
    path builds nothing observable; assertions without a history fail
    loudly rather than deriving a partial loop."""
    recorded: list[tuple[str, Any]] = []
    _route_story_streams(monkeypatch, {}, recorded)

    # No scenario at all.
    bare = _patched_seed("loop-applicant-adopted", lambda case: case.pop("scenario"))
    assert bare.scenario.medical_assertions is None
    plan = derive_medical_assertion_plan(bare, None)
    assert plan.ledger is None
    assert plan.contention_documents == ()

    # A history alone: still no assertion layer, still an empty plan.
    history_only = _patched_seed(
        "loop-applicant-adopted",
        lambda case: case["scenario"].pop("medical_assertions"),
    )
    history = derive_medical_history(history_only)
    assert history is not None
    plan = derive_medical_assertion_plan(history_only, history)
    assert plan.ledger is None
    assert plan.contention_documents == ()
    assert recorded == [], "the absent path constructed a medical-story stream"

    # Assertions without a history are an error, never a partial loop — the
    # seed schema rejects the combination at parse, and the derivation guard
    # holds the same line for a caller that never derived the history.
    with pytest.raises(
        SeedValidationError, match=r"requires scenario\.medical_history"
    ):
        _patched_seed(
            "loop-applicant-adopted",
            lambda case: case["scenario"].pop("medical_history"),
        )
    with pytest.raises(
        MedicalAssertionError, match=r"requires scenario\.medical_history"
    ):
        derive_medical_assertion_plan(_matrix_seeds()["loop-applicant-adopted"], None)
    assert recorded == []


# ---------------------------------------------------------------------------
# R43 opinion-realization gate
# ---------------------------------------------------------------------------


def test_every_opinion_event_has_exactly_one_compatible_document_realization() -> None:
    """R43's realization gate (R27): across every R67 matrix case, every
    ledger opinion — base or sampled response — is realized by exactly one
    binding whose kind matches its event and whose carrier is R8-compatible,
    dated on the opinion's own report date."""
    kind_by_event = {
        "base_report": "opinion_report",
        "supplemental_report": "supplemental_report",
        "deposition": "qme_deposition",
    }
    checked = 0
    response_realizations = 0
    for case_id, _party, _disposition in _MATRIX_ROWS:
        seed = _matrix_seeds()[case_id]
        _history, _trace, plan = _derive(seed)
        assert plan.ledger is not None
        opinion_ids = {opinion.id for opinion in plan.ledger.medical_opinions}
        for binding in plan.contention_documents:
            if binding.medical_opinion_id is not None:
                assert binding.medical_opinion_id in opinion_ids
        for opinion in plan.ledger.medical_opinions:
            realizations = [
                binding
                for binding in plan.contention_documents
                if binding.medical_opinion_id == opinion.id
            ]
            assert len(realizations) == 1, (case_id, opinion.id, realizations)
            realization = realizations[0]
            assert realization.document_kind == kind_by_event[opinion.event_kind]
            if opinion.event_kind == "deposition":
                compatible = frozenset({"DEPOSITION_TRANSCRIPT"})
            elif opinion.event_kind == "supplemental_report":
                compatible = SUPPLEMENTAL_MEDLEGAL_SURFACES
            elif opinion.author_role == "ptp":
                compatible = PTP_CAUSATION_SURFACES
            else:
                compatible = INITIAL_MEDLEGAL_SURFACES | PSYCH_MEDLEGAL_SURFACES
            assert realization.subtype in compatible, (case_id, opinion.id)
            assert realization.proposed_date == opinion.report_date
            checked += 1
            if opinion.event_kind != "base_report":
                response_realizations += 1
    assert checked >= 10
    assert response_realizations >= 1, (
        "no matrix case sampled a response opinion; the realization gate "
        "never saw a supplemental or deposition event"
    )


# ---------------------------------------------------------------------------
# R43 complete-decision-table gate
# ---------------------------------------------------------------------------


def test_r29_disposition_party_matrix_is_exact(monkeypatch: pytest.MonkeyPatch) -> None:
    """R43's decision-table gate (R29/R30), looped over all ten R67 rows.

    The production table equals the independent literal cell for cell; each
    fixture row, forced to fire, constructs exactly its own cell's incidence
    family with the cell's actor and class in the opportunity key, and every
    produced communication is authored by that actor; a defense-eligible row
    outside R30's apportionment/psych concern constructs NO defense stream
    at all — probability zero without a draw."""
    assert assertion_module._R29_DECISION_TABLE == _R29_TABLE_LITERAL
    family_by_cell = {
        ("defense", "determined_adverse"): "defense-contest-incidence",
        ("defense", "completion"): "defense-contest-incidence",
        ("applicant", "determined_adverse"): "applicant-contest-incidence",
        ("applicant", "completion"): "completion-incidence",
    }

    for case_id, party, disposition in _MATRIX_ROWS:
        actor, disposition_class = _R29_TABLE_LITERAL[(party, disposition)]
        recorded: list[tuple[str, Any]] = []
        _route_story_streams(
            monkeypatch,
            _contest_world("objection_only", "supplemental_only"),
            recorded,
        )
        seed = _matrix_seeds()[case_id]
        _history, _trace, plan = _derive(seed)
        monkeypatch.undo()

        incidence = [
            (family, key) for family, key in recorded if family in _INCIDENCE_FAMILIES
        ]
        assert len(incidence) == 1, (case_id, incidence)
        family, key = incidence[0]
        assert family == family_by_cell[(actor, disposition_class)], case_id
        x_key = key[2]
        assert x_key[2] == "opportunity"
        assert x_key[3] == actor, case_id
        assert x_key[4] == disposition_class, case_id
        assert x_key[5] == ("case", seed.case_id, "opinion", "explicit", "opn-01")

        contest = _sampled_contest_documents(plan)
        assert contest, case_id
        communications = [
            binding
            for binding in contest
            if binding.document_kind in ("objection", "supplemental_request")
        ]
        assert communications, case_id
        for binding in communications:
            assert binding.actor_party == actor, case_id
        if disposition_class == "determined_adverse":
            assert contest[0].document_kind == "objection", case_id
        else:
            assert contest[0].document_kind == "supplemental_request", case_id
            assert all(
                binding.document_kind != "objection" for binding in contest
            ), case_id

    # Outside R30 the defense channel does not exist: an adopted applicant
    # contention concerning neither apportionment nor psych constructs no
    # defense stream and no defense document.
    def to_plain_causation(case: dict[str, Any]) -> None:
        contention = case["scenario"]["medical_assertions"]["contentions"][0]
        contention["claim_type"] = "industrial_causation"
        del contention["target_body_part"]
        contention["target_condition_id"] = "cond-00"
        contention["rationale"] = "the lumbar condition arose from the industrial injury"

    outside = _patched_seed("loop-applicant-adopted", to_plain_causation)
    recorded = []
    _route_story_streams(
        monkeypatch, _contest_world("objection_only", "supplemental_only"), recorded
    )
    _history, _trace, plan = _derive(outside)
    monkeypatch.undo()
    assert [f for f, _k in recorded if f in _INCIDENCE_FAMILIES] == []
    assert _sampled_contest_documents(plan) == []
    assert all(
        binding.actor_party != "defense" for binding in plan.contention_documents
    )


# ---------------------------------------------------------------------------
# R43 defense-contest gate
# ---------------------------------------------------------------------------


def test_defense_contest_eligibility_actor_and_theory_propagation_are_exact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R43's defense-contest gate (R30/R51): a sampled defense chain draws
    its theory count once and its weighted-without-replacement selection once
    from chain-keyed streams, and copies the ordered tuple to EVERY
    attorney-authored document in the chain — never to the evaluator's
    supplemental report; an applicant chain draws no theory stream and
    carries no theories."""
    count_table = assertion_module.DEFENSE_THEORY_COUNT_WEIGHTS.value
    forced = _contest_world("objection_supplemental_deposition")
    forced["defense-theory-count"] = lambda *_: _ForcedStream(
        uniform=_selecting_uniform(count_table, 2)
    )
    forced["defense-theory-selection"] = _fire
    recorded: list[tuple[str, Any]] = []
    _route_story_streams(monkeypatch, forced, recorded)
    _history, _trace, plan = _derive(_matrix_seeds()["loop-defense-rejected"])
    monkeypatch.undo()

    # Count forced to 2; selection forced to always take the first remaining
    # member, so the ordered tuple is the first two theories in declaration
    # order — asserted as an independent literal.
    expected = ("insufficient_investigation", "post_termination")
    contest = _sampled_contest_documents(plan)
    kinds = [binding.document_kind for binding in contest]
    assert kinds == [
        "objection",
        "supplemental_request",
        "supplemental_report",
        "qme_deposition",
    ]
    by_kind = {binding.document_kind: binding for binding in contest}
    assert by_kind["objection"].defense_contest_theories == expected
    assert by_kind["supplemental_request"].defense_contest_theories == expected
    assert by_kind["qme_deposition"].defense_contest_theories == expected
    assert by_kind["objection"].actor_party == "defense"
    assert by_kind["qme_deposition"].actor_party == "defense"
    assert by_kind["supplemental_report"].defense_contest_theories == ()
    assert by_kind["supplemental_report"].actor_party is None
    count_streams = [k for f, k in recorded if f == "defense-theory-count"]
    selection_streams = [k for f, k in recorded if f == "defense-theory-selection"]
    assert len(count_streams) == 1
    assert len(selection_streams) == 1
    assert count_streams[0] == selection_streams[0]

    # An applicant chain constructs no theory stream and no theories.
    recorded = []
    _route_story_streams(
        monkeypatch, _contest_world("objection_supplemental"), recorded
    )
    _history, _trace, plan = _derive(_matrix_seeds()["loop-applicant-rejected"])
    monkeypatch.undo()
    assert all(
        family not in ("defense-theory-count", "defense-theory-selection")
        for family, _key in recorded
    )
    for binding in _sampled_contest_documents(plan):
        assert binding.defense_contest_theories == ()


# ---------------------------------------------------------------------------
# R43 branch/truncation gate
# ---------------------------------------------------------------------------


def test_every_contest_path_orders_and_tail_truncates_exactly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R43's branching gate (R29/R31): all six ContestPath literals produce
    exactly their stage sequences in strict causal date order, and every R31
    truncation collapses exactly — ``O→R→S→D → O→R→S → O``, ``R→S→D → R→S``
    (and to nothing), ``O→D → O`` — from the tail, without redraw, with the
    truncated stage's raw draw left burned."""
    stage_kinds = {
        "objection_only": ["objection"],
        "objection_supplemental": [
            "objection",
            "supplemental_request",
            "supplemental_report",
        ],
        "objection_deposition": ["objection", "qme_deposition"],
        "objection_supplemental_deposition": [
            "objection",
            "supplemental_request",
            "supplemental_report",
            "qme_deposition",
        ],
        "supplemental_only": ["supplemental_request", "supplemental_report"],
        "supplemental_deposition": [
            "supplemental_request",
            "supplemental_report",
            "qme_deposition",
        ],
    }

    def run(
        path: str, *, case_id: str, report_date: str | None = None, bands_upper: bool
    ) -> tuple[MedicalAssertionPlan, AssertionTrace]:
        adverse = path if path.startswith("objection") else None
        completion = path if path.startswith("supplemental") else None
        forced = _contest_world(adverse, completion)
        if bands_upper:
            for family in (
                "objection-lag",
                "supplemental-request-lag",
                "supplemental-report-lag",
                "deposition-lag",
            ):
                forced[family] = _upper
        _route_story_streams(monkeypatch, forced)
        if report_date is None:
            seed = _matrix_seeds()[case_id]
        else:
            def move_report(case: dict[str, Any]) -> None:
                case["scenario"]["medical_assertions"]["medical_opinions"][0][
                    "report_date"
                ] = dt.date.fromisoformat(report_date)

            seed = _patched_seed(case_id, move_report)
        _history, trace, plan = _derive(seed)
        monkeypatch.undo()
        return plan, trace

    adverse_case = "loop-applicant-rejected"
    completion_case = "loop-applicant-deferred"

    # Every literal in full: the exact stage order, strictly increasing
    # causal dates, the first stage strictly after the contested report.
    for path, expected_kinds in stage_kinds.items():
        case_id = adverse_case if path.startswith("objection") else completion_case
        plan, _trace = run(path, case_id=case_id, bands_upper=False)
        contest = _sampled_contest_documents(plan)
        assert [b.document_kind for b in contest] == expected_kinds, path
        report_date = plan.ledger.medical_opinions[0].report_date
        dates = [binding.proposed_date for binding in contest]
        assert dates[0] > report_date, path
        assert all(later > earlier for earlier, later in pairwise(dates)), path

    # O→R→S→D → O→R→S: the deposition alone crosses the anchor and drops;
    # its lag draw stays burned.
    plan, trace = run(
        "objection_supplemental_deposition",
        case_id=adverse_case,
        report_date="2025-05-01",
        bands_upper=True,
    )
    contest = _sampled_contest_documents(plan)
    assert [b.document_kind for b in contest] == [
        "objection",
        "supplemental_request",
        "supplemental_report",
    ]
    assert [family for family, _offset in trace.story_raw_date_offsets] == [
        "objection-lag",
        "supplemental-request-lag",
        "supplemental-report-lag",
        "deposition-lag",
    ]
    assert len(plan.ledger.medical_opinions) == 2  # base + supplemental only

    # O→R→S→D → O: the supplemental report crosses the anchor, so R never
    # survives without S — the request is removed with it and the chain
    # keeps only its objection. Both downstream draws stay burned.
    plan, trace = run(
        "objection_supplemental_deposition",
        case_id=adverse_case,
        report_date="2025-08-15",
        bands_upper=True,
    )
    contest = _sampled_contest_documents(plan)
    assert [b.document_kind for b in contest] == ["objection"]
    assert [family for family, _offset in trace.story_raw_date_offsets] == [
        "objection-lag",
        "supplemental-request-lag",
        "supplemental-report-lag",
    ]
    assert len(plan.ledger.medical_opinions) == 1

    # O→D → O: the deposition examining the base report crosses the anchor
    # and drops alone.
    plan, trace = run(
        "objection_deposition",
        case_id=adverse_case,
        report_date="2025-09-15",
        bands_upper=True,
    )
    contest = _sampled_contest_documents(plan)
    assert [b.document_kind for b in contest] == ["objection"]
    assert [family for family, _offset in trace.story_raw_date_offsets] == [
        "objection-lag",
        "deposition-lag",
    ]

    # R→S→D → R→S on a completion chain.
    plan, trace = run(
        "supplemental_deposition",
        case_id=completion_case,
        report_date="2025-06-01",
        bands_upper=True,
    )
    contest = _sampled_contest_documents(plan)
    assert [b.document_kind for b in contest] == [
        "supplemental_request",
        "supplemental_report",
    ]
    assert [family for family, _offset in trace.story_raw_date_offsets] == [
        "supplemental-request-lag",
        "supplemental-report-lag",
        "deposition-lag",
    ]
    assert len(plan.ledger.medical_opinions) == 2

    # R→S → nothing: the supplemental report fails, the request goes with
    # it, and the whole completion chain vanishes without redraw.
    plan, trace = run(
        "supplemental_only",
        case_id=completion_case,
        report_date="2025-10-15",
        bands_upper=True,
    )
    assert _sampled_contest_documents(plan) == []
    assert [family for family, _offset in trace.story_raw_date_offsets] == [
        "supplemental-request-lag",
        "supplemental-report-lag",
    ]
    assert len(plan.ledger.medical_opinions) == 1


# ---------------------------------------------------------------------------
# R43 cap gate
# ---------------------------------------------------------------------------


def test_contention_loop_caps_are_exact_and_jointly_enforced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R43's cap gate (R31): every constant is exact; each cap has a
    constructed encounter case at the explicit seam with its exact failure
    message; an explicit violation FAILS derivation end to end; sampled
    infeasibility truncates from the tail without redraw."""
    assert MAX_CONTENTION_CHAINS_PER_CASE == 3
    assert MAX_BOUND_CONTENTION_DOCUMENTS_PER_CASE == 15
    assert MAX_CONTENTIONS_PER_LOOP_DOCUMENT == 3
    assert MAX_ADVOCACY_LETTERS_PER_CASE == 3
    assert MAX_OBJECTIONS_PER_CASE == 2
    assert MAX_SUPPLEMENTAL_REQUESTS_PER_CASE == 2
    assert MAX_SUPPLEMENTAL_REPORTS_PER_CASE == 2
    assert MAX_QME_AME_DEPOSITIONS_PER_CASE == 1

    def scenario_of(
        entries: list[ContentionDocumentEntry],
        opinions: list[Any] | None = None,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            contention_documents=entries,
            medical_opinions=opinions or [],
            contentions=[],
        )

    def advocacy_entry(index: int, spoken: str, target: str = "opn-90") -> ContentionDocumentEntry:
        return ContentionDocumentEntry(
            id=f"cdoc-{index:02d}",
            document_kind="advocacy",
            target_medical_opinion_id=target,
            actor_party="applicant",
            spoken_contention_ids=[spoken],
        )

    def objection_entry(
        index: int, spoken: str, *, target: str = "opn-90", actor: str = "applicant"
    ) -> ContentionDocumentEntry:
        return ContentionDocumentEntry(
            id=f"cdoc-{index:02d}",
            document_kind="objection",
            target_medical_opinion_id=target,
            actor_party=actor,
            spoken_contention_ids=[spoken],
            defense_contest_theories=(
                ["post_termination"] if actor == "defense" else []
            ),
        )

    def request_entry(index: int, spoken: str) -> ContentionDocumentEntry:
        return ContentionDocumentEntry(
            id=f"cdoc-{index:02d}",
            document_kind="supplemental_request",
            target_medical_opinion_id="opn-90",
            actor_party="applicant",
            spoken_contention_ids=[spoken],
        )

    problems = assertion_module._explicit_contention_document_problems(
        scenario_of([advocacy_entry(i, f"ctn-{i:02d}") for i in range(1, 5)])
    )
    assert (
        "explicit contention documents state 4 advocacy documents; the "
        "per-case cap is 3 and explicit cap violations fail rather than "
        "truncate (R31)"
    ) in problems

    problems = assertion_module._explicit_contention_document_problems(
        scenario_of([objection_entry(i, f"ctn-{i:02d}") for i in range(1, 4)])
    )
    assert (
        "explicit contention documents state 3 objection documents; the "
        "per-case cap is 2 and explicit cap violations fail rather than "
        "truncate (R31)"
    ) in problems

    problems = assertion_module._explicit_contention_document_problems(
        scenario_of([request_entry(i, f"ctn-{i:02d}") for i in range(1, 4)])
    )
    assert (
        "explicit contention documents state 3 supplemental_request "
        "documents; the per-case cap is 2 and explicit cap violations fail "
        "rather than truncate (R31)"
    ) in problems

    problems = assertion_module._explicit_contention_document_problems(
        scenario_of(
            [],
            [
                SimpleNamespace(id=f"opn-{90 + i}", event_kind="supplemental_report")
                for i in range(3)
            ],
        )
    )
    assert (
        "explicit contention documents state 3 supplemental_report "
        "documents; the per-case cap is 2 and explicit cap violations fail "
        "rather than truncate (R31)"
    ) in problems

    problems = assertion_module._explicit_contention_document_problems(
        scenario_of(
            [],
            [
                SimpleNamespace(id=f"opn-{90 + i}", event_kind="deposition")
                for i in range(2)
            ],
        )
    )
    assert (
        "explicit contention documents state 2 qme_deposition documents; "
        "the per-case cap is 1 and explicit cap violations fail rather than "
        "truncate (R31)"
    ) in problems

    problems = assertion_module._explicit_contention_document_problems(
        scenario_of(
            [advocacy_entry(i, f"ctn-{i:02d}") for i in range(1, 4)]
            + [objection_entry(4, "ctn-04"), objection_entry(5, "ctn-05")]
            + [request_entry(6, "ctn-06"), request_entry(7, "ctn-07")],
            [
                SimpleNamespace(id=f"opn-{80 + i}", event_kind="base_report")
                for i in range(9)
            ],
        )
    )
    assert (
        "explicit opinions and contention documents bind 16 documents; the "
        "per-case bound-document cap is 15 (R31)"
    ) in problems

    problems = assertion_module._explicit_contention_document_problems(
        scenario_of(
            [
                objection_entry(1, "ctn-01", target="opn-90"),
                objection_entry(2, "ctn-02", target="opn-91"),
                objection_entry(3, "ctn-03", target="opn-90", actor="defense"),
                objection_entry(4, "ctn-04", target="opn-91", actor="defense"),
            ]
        )
    )
    assert (
        "explicit contention documents form 4 contest chains; the per-case "
        "chain cap is 3 (R31)"
    ) in problems

    # End to end: an explicit violation FAILS the derivation — two authored
    # deposition opinions against the frozen cap of one.
    def author_two_depositions(case: dict[str, Any]) -> None:
        opinions = case["scenario"]["medical_assertions"]["medical_opinions"]
        for index, day in ((2, "2025-03-01"), (3, "2025-05-01")):
            opinions.append(
                {
                    "id": f"opn-{index:02d}",
                    "author_role": "qme",
                    "report_stage": "final",
                    "report_date": dt.date.fromisoformat(day),
                    "apportionment_state": "determined",
                    "determination_kind": "unable_to_approximate",
                    "determination_rationale": (
                        "the contributions cannot be approximated on this record"
                    ),
                    "examination_performed": False,
                    "event_kind": "deposition",
                    "responds_to_opinion_id": "opn-01",
                    "revision_kind": "unchanged_additional_reasoning",
                    "revision_rationale": (
                        "the prior conclusions stand under examination"
                    ),
                }
            )

    over_cap = _patched_seed("loop-applicant-adopted", author_two_depositions)
    with pytest.raises(
        MedicalAssertionError,
        match=r"2 qme_deposition documents; the per-case cap is 1",
    ):
        derive_medical_assertion_plan(over_cap, derive_medical_history(over_cap))

    # End to end: sampled infeasibility truncates from the tail without
    # redraw. Two contentions and two base reports force four provisional
    # size-one letters; the fourth is suppressed at the advocacy cap and the
    # first three commit in composition order — and the per-kind cap and the
    # 15-document total are enforced by the same committing counters.
    def add_second_pair(case: dict[str, Any]) -> None:
        block = case["scenario"]["medical_assertions"]
        block["contentions"].append(
            {
                "id": "ctn-02",
                "claim_type": "industrial_causation",
                "party": "applicant",
                "target_condition_id": "cond-00",
                "rationale": "the lumbar condition arose from the industrial injury",
            }
        )
        block["medical_opinions"].append(
            {
                "id": "opn-02",
                "author_role": "ptp",
                "report_stage": "interim",
                "report_date": dt.date.fromisoformat("2024-08-01"),
                "apportionment_state": "deferred",
                "rationale": "treatment continues with interval findings",
            }
        )

    crowded = _patched_seed("loop-applicant-adopted", add_second_pair)
    forced = {
        "advocacy-incidence": _fire,
        "advocacy-bundle-size": _fire,
        "applicant-contest-incidence": _miss,
        "completion-incidence": _miss,
        "defense-contest-incidence": _miss,
    }
    _route_story_streams(monkeypatch, forced)
    _history, _trace, plan = _derive(crowded)
    monkeypatch.undo()
    letters = [
        binding
        for binding in plan.contention_documents
        if binding.document_kind == "advocacy" and binding.source == "sampled"
    ]
    assert len(letters) == MAX_ADVOCACY_LETTERS_PER_CASE
    assert [letter.target_medical_opinion_id for letter in letters] == [
        "opn-01",
        "opn-01",
        "opn-02",
    ]
    spoken = [letter.spoken_contention_ids for letter in letters]
    assert sorted(spoken[:2]) == [("ctn-01",), ("ctn-02",)]
    assert len(spoken[2]) == 1
    assert len(plan.contention_documents) == 5  # two realizations + three letters

    # The per-document contention cap encountered: four contentions firing
    # the same chain split into documents of three and one — bundled at the
    # cap, membership in canonical order, never a four-contention document.
    def author_four_defense_contentions(case: dict[str, Any]) -> None:
        conditions = case["scenario"]["medical_history"]["conditions"]
        block = case["scenario"]["medical_assertions"]
        endorses = ["ctn-01"]
        reviewed = ["cond-00"]
        for index, label in enumerate(
            ("essential hypertension", "type 2 diabetes", "cervical spondylosis"),
            start=1,
        ):
            conditions.append(
                {
                    "label": label,
                    "origin": "nonindustrial",
                    "severity": "moderate",
                    "trajectory": "stable",
                    "symptomatic_before_doi": True,
                }
            )
            block["contentions"].append(
                {
                    "id": f"ctn-{index + 1:02d}",
                    "claim_type": "apportionment_defense",
                    "party": "defense",
                    "target_condition_id": f"cond-{index:02d}",
                    "rationale": f"{label} contributes to the present disability",
                }
            )
            endorses.append(f"ctn-{index + 1:02d}")
            reviewed.append(f"cond-{index:02d}")
        opinion = block["medical_opinions"][0]
        opinion["endorses_contention_ids"] = endorses
        opinion["reviewed_condition_ids"] = reviewed

    four_way = _patched_seed("loop-defense-adopted", author_four_defense_contentions)
    _route_story_streams(monkeypatch, _contest_world("objection_only"))
    _history, _trace, plan = _derive(four_way)
    monkeypatch.undo()
    objections = [
        binding
        for binding in plan.contention_documents
        if binding.document_kind == "objection"
    ]
    assert [binding.spoken_contention_ids for binding in objections] == [
        ("ctn-01", "ctn-02", "ctn-03"),
        ("ctn-04",),
    ]
    assert all(
        len(binding.spoken_contention_ids) <= MAX_CONTENTIONS_PER_LOOP_DOCUMENT
        for binding in plan.contention_documents
        if binding.document_kind != "opinion_report"
    )
    # …while the base report realization is EXEMPT: R35 makes it speak its
    # full four-member disposition union, which is why the communication cap
    # never binds the internal realization record.
    realization = next(
        binding
        for binding in plan.contention_documents
        if binding.document_kind == "opinion_report"
    )
    assert realization.spoken_contention_ids == (
        "ctn-01",
        "ctn-02",
        "ctn-03",
        "ctn-04",
    )


# ---------------------------------------------------------------------------
# R43 IDs-last gate
# ---------------------------------------------------------------------------


def test_response_and_document_ids_are_assigned_in_one_final_subphased_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R43's IDs-last gate (R32/R47 subphases 4-5): sampled response opinions
    take the first unused ``opn-`` suffixes after ALL base entries, their
    rows the first unused ``app-`` suffixes, bindings the first unused
    ``cdoc-`` suffixes in plan composition order, and every draft reference
    resolves — no placeholder survives, and authored IDs are never moved."""

    def rename_and_allocate(case: dict[str, Any]) -> None:
        block = case["scenario"]["medical_assertions"]
        opinion = block["medical_opinions"][0]
        opinion["id"] = "opn-05"
        opinion["determination_kind"] = "allocated"
        opinion["determination_rationale"] = "the split follows the imaging severity"
        block["apportionment_assertions"] = [
            {
                "id": "app-01",
                "opinion_id": "opn-05",
                "body_part": "lumbar_spine",
                "industrial_percent": 80,
                "nonindustrial_percent": 20,
                "basis_kinds": ["preexisting_degenerative_pathology"],
                "condition_ids": ["cond-00"],
                "description": "chronic lumbar disability limiting weight-bearing",
                "disability_causation_stated": True,
                "reasonable_medical_probability": True,
                "causal_rationale": (
                    "degenerative pathology contributes to the disability"
                ),
                "percentage_rationale": "the share reflects the imaging severity",
            }
        ]

    seed = _patched_seed("loop-applicant-concurred", rename_and_allocate)
    _route_story_streams(
        monkeypatch, _contest_world("objection_supplemental_deposition")
    )
    _history, _trace, plan = _derive(seed)
    monkeypatch.undo()
    ledger = plan.ledger
    assert ledger is not None

    # Response opinions take the first unused suffixes after the base
    # entries, in creation order: base opn-05 leaves opn-01/opn-02 free.
    assert [o.id for o in ledger.medical_opinions] == ["opn-05", "opn-01", "opn-02"]
    assert [o.event_kind for o in ledger.medical_opinions] == [
        "base_report",
        "supplemental_report",
        "deposition",
    ]
    supplemental, deposition = ledger.medical_opinions[1], ledger.medical_opinions[2]
    assert supplemental.responds_to_opinion_id == "opn-05"
    assert deposition.responds_to_opinion_id == "opn-01"
    assert deposition.supersedes_opinion_id in (None, "opn-01")

    # Rows: the authored app-01 stays; each response restates the allocated
    # predecessor surface and takes the next unused app suffix.
    rows_by_opinion: dict[str, list[str]] = {}
    for row in ledger.apportionment_assertions:
        rows_by_opinion.setdefault(row.opinion_id, []).append(row.id)
    assert rows_by_opinion["opn-05"] == ["app-01"]
    assert rows_by_opinion["opn-01"] == ["app-02"]
    assert rows_by_opinion["opn-02"] == ["app-03"]

    # Bindings: first unused cdoc suffixes in plan composition order —
    # realization, objection, request, supplemental report, deposition.
    assert [binding.id for binding in plan.contention_documents] == [
        "cdoc-01",
        "cdoc-02",
        "cdoc-03",
        "cdoc-04",
        "cdoc-05",
    ]
    assert [binding.document_kind for binding in plan.contention_documents] == [
        "opinion_report",
        "objection",
        "supplemental_request",
        "supplemental_report",
        "qme_deposition",
    ]
    by_kind = {binding.document_kind: binding for binding in plan.contention_documents}
    assert by_kind["opinion_report"].medical_opinion_id == "opn-05"
    assert by_kind["supplemental_report"].medical_opinion_id == "opn-01"
    assert by_kind["qme_deposition"].medical_opinion_id == "opn-02"
    assert by_kind["qme_deposition"].target_medical_opinion_id == "opn-01"

    # No placeholder survives the final pass anywhere.
    for opinion in ledger.medical_opinions:
        for value in (
            opinion.id,
            opinion.responds_to_opinion_id,
            opinion.supersedes_opinion_id,
        ):
            assert value is None or "response:" not in value
    for binding in plan.contention_documents:
        for value in (binding.medical_opinion_id, binding.target_medical_opinion_id):
            assert value is None or "response:" not in value

    # The same forced world over the unpatched row (base opn-01) allocates
    # opn-02/opn-03 — the suffix follows the used set, in one final pass.
    _route_story_streams(
        monkeypatch, _contest_world("objection_supplemental_deposition")
    )
    _history, _trace, unpatched = _derive(_matrix_seeds()["loop-applicant-concurred"])
    monkeypatch.undo()
    assert [o.id for o in unpatched.ledger.medical_opinions] == [
        "opn-01",
        "opn-02",
        "opn-03",
    ]


# ---------------------------------------------------------------------------
# R43 explicit-authority gate
# ---------------------------------------------------------------------------


def test_explicit_contention_documents_are_authoritative_below_controls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R43's explicit-authority gate (R40/R41): an explicit opinion-bound
    entry REPLACES the required realization in place with its authored
    carrier and hard date; explicit advocacy and objections keep their
    authored dates, spoken sets and theories verbatim; and fully reserved
    sampled duplicates are suppressed without replacement — the sampled
    layer never redraws, repairs, or duplicates authored paper. Planner
    ``documents:`` controls sit above this seam at R77 step 6."""

    def author_documents(case: dict[str, Any]) -> None:
        case["scenario"]["medical_assertions"]["contention_documents"] = [
            {
                "id": "cdoc-01",
                "document_kind": "opinion_report",
                "medical_opinion_id": "opn-01",
                "subtype": "QME_REPORT_INITIAL",
                "doc_date": dt.date.fromisoformat("2024-12-20"),
            },
            {
                "id": "cdoc-02",
                "document_kind": "advocacy",
                "target_medical_opinion_id": "opn-01",
                "actor_party": "applicant",
                "spoken_contention_ids": ["ctn-01"],
                "subtype": "ADVOCACY_LETTERS_QME",
                "doc_date": dt.date.fromisoformat("2024-11-15"),
            },
            {
                "id": "cdoc-03",
                "document_kind": "objection",
                "target_medical_opinion_id": "opn-01",
                "actor_party": "defense",
                "spoken_contention_ids": ["ctn-01"],
                "doc_date": dt.date.fromisoformat("2025-01-15"),
                "defense_contest_theories": ["post_termination"],
            },
        ]

    seed = _patched_seed("loop-applicant-adopted", author_documents)
    forced = _contest_world("objection_only")
    forced["advocacy-incidence"] = _fire  # the sampled letter must be reserved out
    _route_story_streams(monkeypatch, forced)
    _history, _trace, plan = _derive(seed)
    monkeypatch.undo()

    # Exactly the three authored documents: the realization was replaced in
    # place, the fully reserved sampled letter and sampled objection were
    # suppressed without replacement.
    assert [binding.id for binding in plan.contention_documents] == [
        "cdoc-01",
        "cdoc-02",
        "cdoc-03",
    ]
    realization, advocacy, objection = plan.contention_documents
    assert all(binding.source == "explicit" for binding in plan.contention_documents)

    assert realization.document_kind == "opinion_report"
    assert realization.medical_opinion_id == "opn-01"
    assert realization.subtype == "QME_REPORT_INITIAL"  # authored, not the default
    assert realization.doc_date == dt.date(2024, 12, 20)
    assert realization.proposed_date == dt.date(2024, 12, 20)

    assert advocacy.document_kind == "advocacy"
    assert advocacy.doc_date == dt.date(2024, 11, 15)
    assert advocacy.spoken_contention_ids == ("ctn-01",)
    assert advocacy.actor_party == "applicant"
    assert advocacy.subtype == "ADVOCACY_LETTERS_QME"

    assert objection.document_kind == "objection"
    assert objection.doc_date == dt.date(2025, 1, 15)
    assert objection.actor_party == "defense"
    assert objection.defense_contest_theories == ("post_termination",)
    assert objection.subtype == "ADVOCACY_LETTERS_PTP_QME_AME"
    assert objection.template_subtype == "OBJECTION_TO_QME_AME_REPORT"

    # Authority is stable: a second derivation reproduces the same plan byte
    # for byte — nothing about the authored set is ever redrawn.
    _route_story_streams(monkeypatch, forced)
    _history, _trace, again = _derive(seed)
    monkeypatch.undo()
    assert [b.model_dump() for b in again.contention_documents] == [
        b.model_dump() for b in plan.contention_documents
    ]
    assert again.ledger.model_dump() == plan.ledger.model_dump()


# ---------------------------------------------------------------------------
# R43 mixed-composition gate
# ---------------------------------------------------------------------------


def test_explicit_partial_overlap_suppresses_only_the_collision_without_redraw_or_repack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R43's mixed-composition gate (R41): when an explicit document reserves
    PART of a sampled bundle, only the colliding contention leaves the
    sampled document — remaining membership is preserved without redraw or
    repacking, unreserved stages keep their full membership, and the
    pre-document decision streams are byte-identical with and without the
    explicit entries."""

    def widen(case: dict[str, Any]) -> None:
        case["scenario"]["medical_history"]["conditions"].append(
            {
                "label": "essential hypertension",
                "origin": "nonindustrial",
                "severity": "moderate",
                "trajectory": "stable",
                "symptomatic_before_doi": True,
            }
        )
        block = case["scenario"]["medical_assertions"]
        block["contentions"].append(
            {
                "id": "ctn-02",
                "claim_type": "apportionment_defense",
                "party": "defense",
                "target_condition_id": "cond-01",
                "rationale": "hypertension contributes to the present disability",
            }
        )
        opinion = block["medical_opinions"][0]
        opinion["endorses_contention_ids"] = ["ctn-01", "ctn-02"]
        opinion["reviewed_condition_ids"] = ["cond-00", "cond-01"]

    def with_explicit(case: dict[str, Any]) -> None:
        widen(case)
        case["scenario"]["medical_assertions"]["contention_documents"] = [
            {
                "id": "cdoc-01",
                "document_kind": "advocacy",
                "target_medical_opinion_id": "opn-01",
                "actor_party": "defense",
                "spoken_contention_ids": ["ctn-01"],
                "doc_date": dt.date.fromisoformat("2024-11-15"),
            },
            {
                "id": "cdoc-02",
                "document_kind": "objection",
                "target_medical_opinion_id": "opn-01",
                "actor_party": "applicant",
                "spoken_contention_ids": ["ctn-01"],
                "doc_date": dt.date.fromisoformat("2025-01-15"),
            },
        ]

    bundle_sizes = ((1, Fraction(10, 17)), (2, Fraction(7, 17)))
    forced = _contest_world("objection_supplemental")
    forced["advocacy-incidence"] = _fire
    forced["advocacy-bundle-size"] = lambda *_: _ForcedStream(
        uniform=_selecting_uniform(bundle_sizes, 2)
    )
    watched = (
        "advocacy-incidence",
        "advocacy-bundle-size",
        "applicant-contest-incidence",
        "contest-path",
    )

    recorded_a: list[tuple[str, Any]] = []
    _route_story_streams(monkeypatch, forced, recorded_a)
    _history, _trace, baseline = _derive(
        _patched_seed("loop-defense-adopted", widen)
    )
    monkeypatch.undo()

    letters = [
        b
        for b in baseline.contention_documents
        if b.document_kind == "advocacy" and b.source == "sampled"
    ]
    assert [letter.spoken_contention_ids for letter in letters] == [
        ("ctn-01", "ctn-02")
    ]
    contest = _sampled_contest_documents(baseline)
    assert [b.document_kind for b in contest] == [
        "objection",
        "supplemental_request",
        "supplemental_report",
    ]
    assert contest[0].spoken_contention_ids == ("ctn-01", "ctn-02")
    assert contest[1].spoken_contention_ids == ("ctn-01", "ctn-02")

    recorded_b: list[tuple[str, Any]] = []
    _route_story_streams(monkeypatch, forced, recorded_b)
    _history, _trace, overlapped = _derive(
        _patched_seed("loop-defense-adopted", with_explicit)
    )
    monkeypatch.undo()

    # The sampled letter keeps its provisional membership minus exactly the
    # reserved contention — never repacked, never regrown, never redrawn.
    letters = [
        b
        for b in overlapped.contention_documents
        if b.document_kind == "advocacy" and b.source == "sampled"
    ]
    assert [letter.spoken_contention_ids for letter in letters] == [("ctn-02",)]

    # The sampled objection loses only the collision; the unreserved request
    # and the supplemental report keep the chunk's full membership.
    contest = _sampled_contest_documents(overlapped)
    assert [b.document_kind for b in contest] == [
        "objection",
        "supplemental_request",
        "supplemental_report",
    ]
    assert contest[0].spoken_contention_ids == ("ctn-02",)
    assert contest[1].spoken_contention_ids == ("ctn-01", "ctn-02")
    assert contest[2].spoken_contention_ids == ("ctn-01", "ctn-02")

    # The explicit documents stand verbatim beside the sampled remainder.
    explicit = [b for b in overlapped.contention_documents if b.source == "explicit"]
    assert [(b.id, b.document_kind) for b in explicit] == [
        ("cdoc-01", "advocacy"),
        ("cdoc-02", "objection"),
    ]

    # No redraw: every pre-document decision stream is identical with and
    # without the explicit entries.
    for family in watched:
        assert [k for f, k in recorded_a if f == family] == [
            k for f, k in recorded_b if f == family
        ], family


# ---------------------------------------------------------------------------
# R43 non-recursion gate
# ---------------------------------------------------------------------------


def test_sampled_supplemental_never_recurses_beyond_one_deposition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R43's non-recursion gate (R29): even with every incidence channel
    forced certain, a sampled supplemental opinion never becomes the source
    of another sampled chain — every opportunity references the explicit
    base report, the only document examining the supplemental is its own
    chain's single deposition, and nothing ever targets the deposition."""
    forced = _contest_world(None, "supplemental_deposition")
    recorded: list[tuple[str, Any]] = []
    _route_story_streams(monkeypatch, forced, recorded)
    _history, _trace, plan = _derive(_matrix_seeds()["loop-applicant-deferred"])
    monkeypatch.undo()

    ledger = plan.ledger
    assert ledger is not None
    assert [o.event_kind for o in ledger.medical_opinions] == [
        "base_report",
        "supplemental_report",
        "deposition",
    ]
    base, supplemental, deposition = ledger.medical_opinions

    # Every constructed opportunity references the explicit base report —
    # no incidence stream is ever keyed by a sampled response opinion.
    incidence_keys = [key for family, key in recorded if family in _INCIDENCE_FAMILIES]
    assert incidence_keys, "no opportunity was constructed"
    for key in incidence_keys:
        opinion_atom = key[2][5]
        assert opinion_atom == (
            "case",
            "loop-applicant-deferred",
            "opinion",
            "explicit",
            "opn-01",
        )
    assert len(incidence_keys) == 1  # one contention x one base report

    kinds = sorted(b.document_kind for b in plan.contention_documents)
    assert kinds == [
        "opinion_report",
        "qme_deposition",
        "supplemental_report",
        "supplemental_request",
    ]
    targets = {
        b.document_kind: b.target_medical_opinion_id
        for b in plan.contention_documents
    }
    assert targets["supplemental_request"] == base.id
    assert targets["supplemental_report"] == base.id
    assert targets["qme_deposition"] == supplemental.id
    assert deposition.responds_to_opinion_id == supplemental.id
    assert all(
        b.target_medical_opinion_id != deposition.id
        for b in plan.contention_documents
    ), "a document targeted the terminal deposition"

    # Certain incidence again over the completed world reproduces the same
    # plan — the recursion door stays closed on rederivation too.
    _route_story_streams(monkeypatch, forced)
    _history, _trace, again = _derive(_matrix_seeds()["loop-applicant-deferred"])
    monkeypatch.undo()
    assert again.ledger.model_dump() == ledger.model_dump()
    assert [b.model_dump() for b in again.contention_documents] == [
        b.model_dump() for b in plan.contention_documents
    ]


# ---------------------------------------------------------------------------
# R43 supplemental/deposition form gate
# ---------------------------------------------------------------------------


def test_supplemental_and_deposition_preceding_report_bindings_are_exact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R43's supplemental-form gate at the plan layer (R35/R36): a sampled
    supplemental report binds its own response opinion and targets the exact
    predecessor report; a deposition examining the supplemental binds the
    deposition opinion against the supplemental, while a deposition on an
    objection-deposition chain examines the base report directly."""
    _route_story_streams(
        monkeypatch, _contest_world("objection_supplemental_deposition")
    )
    _history, _trace, plan = _derive(_matrix_seeds()["loop-applicant-rejected"])
    monkeypatch.undo()
    ledger = plan.ledger
    base, supplemental, deposition = ledger.medical_opinions
    assert supplemental.event_kind == "supplemental_report"
    assert supplemental.responds_to_opinion_id == base.id
    assert deposition.event_kind == "deposition"
    assert deposition.responds_to_opinion_id == supplemental.id

    by_kind = {b.document_kind: b for b in _sampled_contest_documents(plan)}
    assert by_kind["supplemental_report"].medical_opinion_id == supplemental.id
    assert by_kind["supplemental_report"].target_medical_opinion_id == base.id
    assert by_kind["supplemental_report"].subtype == "SUPPLEMENTAL_QME_AME_REPORT"
    assert (
        by_kind["supplemental_report"].template_subtype
        == "SUPPLEMENTAL_QME_AME_REPORT"
    )
    assert by_kind["qme_deposition"].medical_opinion_id == deposition.id
    assert by_kind["qme_deposition"].target_medical_opinion_id == supplemental.id
    assert by_kind["qme_deposition"].subtype == "DEPOSITION_TRANSCRIPT"
    assert (
        by_kind["qme_deposition"].template_subtype == "DEPOSITION_TRANSCRIPT_QME_AME"
    )
    assert by_kind["qme_deposition"].proposed_date > supplemental.report_date

    # Without a supplemental in the chain the deposition examines the base.
    _route_story_streams(monkeypatch, _contest_world("objection_deposition"))
    _history, _trace, direct = _derive(_matrix_seeds()["loop-applicant-rejected"])
    monkeypatch.undo()
    base, deposition = direct.ledger.medical_opinions
    assert deposition.event_kind == "deposition"
    assert deposition.responds_to_opinion_id == base.id
    by_kind = {b.document_kind: b for b in _sampled_contest_documents(direct)}
    assert by_kind["qme_deposition"].medical_opinion_id == deposition.id
    assert by_kind["qme_deposition"].target_medical_opinion_id == base.id
    assert by_kind["qme_deposition"].proposed_date > base.report_date


# ---------------------------------------------------------------------------
# R43 binding-matrix gate
# ---------------------------------------------------------------------------


def test_every_contention_document_kind_carries_exact_r35_bindings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R43's binding-matrix gate (R35): one forced world producing all six
    document kinds, each asserted against the exact R35 row — opinion
    binding, target binding, spoken set, actor, carrier and internal
    template subtype — with the substrate-only keys appearing ONLY as
    template subtypes, never as carriers."""
    forced = _contest_world("objection_supplemental_deposition")
    forced["advocacy-incidence"] = _fire
    _route_story_streams(monkeypatch, forced)
    _history, _trace, plan = _derive(_matrix_seeds()["loop-applicant-rejected"])
    monkeypatch.undo()

    ledger = plan.ledger
    base, supplemental, deposition = ledger.medical_opinions
    counts: dict[str, int] = {}
    for binding in plan.contention_documents:
        counts[binding.document_kind] = counts.get(binding.document_kind, 0) + 1
    assert counts == {
        "opinion_report": 1,
        "advocacy": 1,
        "objection": 1,
        "supplemental_request": 1,
        "supplemental_report": 1,
        "qme_deposition": 1,
    }
    by_kind = {b.document_kind: b for b in plan.contention_documents}

    realization = by_kind["opinion_report"]
    assert realization.medical_opinion_id == base.id
    assert realization.target_medical_opinion_id is None
    assert realization.actor_party is None
    assert realization.defense_contest_theories == ()
    assert realization.spoken_contention_ids == ("ctn-01",)  # the disposition union
    assert realization.subtype == "QME_COMPREHENSIVE_REPORT"  # (qme, final) default
    assert realization.template_subtype is None
    assert realization.proposed_date == base.report_date

    advocacy = by_kind["advocacy"]
    assert advocacy.medical_opinion_id is None
    assert advocacy.target_medical_opinion_id == base.id
    assert advocacy.actor_party == "applicant"
    assert advocacy.spoken_contention_ids == ("ctn-01",)
    assert advocacy.subtype == "ADVOCACY_LETTERS_QME"  # the qme role carrier
    assert advocacy.template_subtype == "ADVOCACY_LETTERS_QME"
    lead = (base.report_date - advocacy.proposed_date).days
    assert 14 <= lead <= 45

    objection = by_kind["objection"]
    assert objection.medical_opinion_id is None
    assert objection.target_medical_opinion_id == base.id
    assert objection.actor_party == "applicant"
    assert objection.spoken_contention_ids == ("ctn-01",)
    assert objection.subtype == "ADVOCACY_LETTERS_PTP_QME_AME"
    assert objection.template_subtype == "OBJECTION_TO_QME_AME_REPORT"

    request = by_kind["supplemental_request"]
    assert request.medical_opinion_id is None
    assert request.target_medical_opinion_id == base.id
    assert request.actor_party == "applicant"
    assert request.spoken_contention_ids == ("ctn-01",)
    assert request.subtype == "ADVOCACY_LETTERS_PTP_QME_AME"
    assert request.template_subtype == "REQUEST_SUPPLEMENTAL_QME_AME_REPORT"

    report = by_kind["supplemental_report"]
    assert report.medical_opinion_id == supplemental.id
    assert report.target_medical_opinion_id == base.id
    assert report.actor_party is None
    assert report.spoken_contention_ids == ("ctn-01",)
    assert report.subtype == "SUPPLEMENTAL_QME_AME_REPORT"
    assert report.template_subtype == "SUPPLEMENTAL_QME_AME_REPORT"

    transcript = by_kind["qme_deposition"]
    assert transcript.medical_opinion_id == deposition.id
    assert transcript.target_medical_opinion_id == supplemental.id
    assert transcript.actor_party == "applicant"
    assert transcript.spoken_contention_ids == ("ctn-01",)
    assert transcript.subtype == "DEPOSITION_TRANSCRIPT"
    assert transcript.template_subtype == "DEPOSITION_TRANSCRIPT_QME_AME"

    # The substrate-only registry keys never surface as carriers (R2/R35).
    substrate_only = {
        "OBJECTION_TO_QME_AME_REPORT",
        "REQUEST_SUPPLEMENTAL_QME_AME_REPORT",
        "DEPOSITION_TRANSCRIPT_QME_AME",
    }
    for binding in plan.contention_documents:
        assert binding.subtype not in substrate_only
    # …and every carrier that is R8-governed sits in its governed set.
    assert advocacy.subtype in ADVOCACY_LETTER_SURFACES
    assert realization.subtype in INITIAL_MEDLEGAL_SURFACES
