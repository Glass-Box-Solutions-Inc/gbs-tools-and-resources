"""Applicant-side vs defense-side case files (ISC-75..84).

The load-bearing test in this file is
:func:`test_mirrored_seeds_produce_identical_case_facts`. Everything else checks
that the *file* changed; that one checks that the *case* did not. If perspective
ever leaks into a fact-producing RNG stream, the whole feature is a lie — two
files that are supposed to be two views of one injury would describe two
different injuries — and that test is what catches it.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from conftest import requires_substrate
from wc_caseload_engine.doc_controls import DocumentCandidate, resolve_document_controls
from wc_caseload_engine.lifecycle_bridge import (
    ROLE_APPLICANT_ATTORNEY,
    ROLE_COURT,
    ROLE_DEFENSE_ATTORNEY,
    ROLE_EMPLOYER,
)
from wc_caseload_engine.perspective import (
    FLOOR_PRIORITY,
    PERSPECTIVE_PROFILES,
    ROLE_INJURED_WORKER,
    WORK_PRODUCT_SWAP,
    EmissionProfile,
    apply_perspective,
    document_roles,
    file_owner_firm,
    profile_for,
    scaled_count,
    swap_subtype,
)
from wc_caseload_engine.planner import build_case_plan
from wc_caseload_engine.seeds import CaseSeed, parse_case_seed
from wc_caseload_engine.taxonomy import effective_taxonomy

APPLICANT_ONLY_SUBTYPES = (
    "CLIENT_INTAKE_CORRESPONDENCE",
    "CLIENT_STATUS_LETTERS",
    "ADVOCACY_LETTERS_PTP",
    "ADVOCACY_LETTERS_QME",
    "ADVOCACY_LETTERS_AME",
    "ADVOCACY_LETTERS_PTP_QME_AME",
)


# ---------------------------------------------------------------------------
# ISC-75 — schema: the field, its default, its enum
# ---------------------------------------------------------------------------


def test_perspective_defaults_to_applicant(minimal_case: dict[str, Any]) -> None:
    """A seed written before this field existed still loads, unchanged."""
    seed = parse_case_seed(minimal_case)
    assert seed.perspective == "applicant"


@pytest.mark.parametrize("value", ["applicant", "defense"])
def test_perspective_accepts_both_sides(minimal_case: dict[str, Any], value: str) -> None:
    seed = parse_case_seed({**minimal_case, "perspective": value})
    assert seed.perspective == value


def test_perspective_rejects_anything_else(minimal_case: dict[str, Any]) -> None:
    """A typo must fail loudly, not silently generate an applicant file."""
    with pytest.raises(ValidationError) as excinfo:
        CaseSeed.model_validate({**minimal_case, "perspective": "carrier"})
    assert "perspective" in str(excinfo.value)


def test_perspective_is_top_level_not_a_document_control(
    minimal_case: dict[str, Any],
) -> None:
    """It governs the whole file, so it sits beside case_id — not under documents."""
    with pytest.raises(ValidationError):
        CaseSeed.model_validate(
            {**minimal_case, "documents": {"perspective": "defense"}}
        )


def test_perspective_changes_the_seed_hash(minimal_case: dict[str, Any]) -> None:
    """Two files of one claim are two different seeds, and must hash differently."""
    applicant = parse_case_seed({**minimal_case, "perspective": "applicant"})
    defense = parse_case_seed({**minimal_case, "perspective": "defense"})
    assert applicant.seed_hash() != defense.seed_hash()


# ---------------------------------------------------------------------------
# ISC-76 — the work-product swap
# ---------------------------------------------------------------------------


@requires_substrate
def test_every_swap_key_and_value_is_canonical_work_product() -> None:
    """A taxonomy resync that renames one of these must fail here, not in a manifest."""
    taxonomy = effective_taxonomy()
    for applicant_key, defense_key in WORK_PRODUCT_SWAP.items():
        assert taxonomy.is_canonical(applicant_key), applicant_key
        assert taxonomy.is_canonical(defense_key), defense_key
        assert taxonomy.parent_of(applicant_key) == "WORK_PRODUCT"
        assert taxonomy.parent_of(defense_key) == "WORK_PRODUCT"


def test_swap_is_defense_only() -> None:
    assert swap_subtype("TRIAL_BRIEF", "applicant") == "TRIAL_BRIEF"
    assert swap_subtype("TRIAL_BRIEF", "defense") == "DEFENSE_TRIAL_BRIEF"


def test_shared_work_product_does_not_swap() -> None:
    """Both sides build a medical chronology, and both call it the same thing."""
    for subtype in ("MEDICAL_CHRONOLOGY_TIMELINE", "DEPOSITION_SUMMARY"):
        assert swap_subtype(subtype, "defense") == subtype


@requires_substrate
def test_defense_file_swaps_applicant_work_product(defense_seed: CaseSeed) -> None:
    """ISC-76: a defense file carries defense work product and no applicant memos."""
    applicant_plan = build_case_plan(_mirror(defense_seed, "applicant"))
    defense_plan = build_case_plan(defense_seed)

    applicant_subtypes = {doc.subtype for doc in applicant_plan.documents}
    defense_subtypes = {doc.subtype for doc in defense_plan.documents}

    swapped = applicant_subtypes & set(WORK_PRODUCT_SWAP)
    assert swapped, "the probe seed must produce at least one swappable memo"
    for applicant_key in swapped:
        assert applicant_key not in defense_subtypes
        assert WORK_PRODUCT_SWAP[applicant_key] in defense_subtypes


# ---------------------------------------------------------------------------
# ISC-77 — the profile table itself
# ---------------------------------------------------------------------------


@requires_substrate
def test_every_profile_key_is_a_taxonomy_key() -> None:
    """The table is data; a stale key in it would silently stop applying."""
    taxonomy = effective_taxonomy()
    for key in PERSPECTIVE_PROFILES:
        assert taxonomy.is_type(key) or taxonomy.is_canonical(key), key


@requires_substrate
def test_every_floor_subtype_is_canonical() -> None:
    taxonomy = effective_taxonomy()
    for key, profile in PERSPECTIVE_PROFILES.items():
        for subtype in profile.floor:
            assert taxonomy.is_canonical(subtype), f"{key} floor: {subtype}"


def test_every_profile_row_explains_itself() -> None:
    """Tuning is one edit, which only works if the numbers say why they are."""
    for key, profile in PERSPECTIVE_PROFILES.items():
        assert profile.rationale, f"{key} has weights but no rationale"


def test_a_subtype_row_beats_its_parent_type_row() -> None:
    """SETTLEMENT_DEMAND_LETTER is CORRESPONDENCE, but has its own row."""
    own = profile_for("SETTLEMENT_DEMAND_LETTER", "CORRESPONDENCE")
    assert own is PERSPECTIVE_PROFILES["SETTLEMENT_DEMAND_LETTER"]
    inherited = profile_for("CLAIMS_DIARY_NOTE", "CLAIMS_ADMINISTRATION")
    assert inherited is PERSPECTIVE_PROFILES["CLAIMS_ADMINISTRATION"]
    assert profile_for("DEPOSITION_TRANSCRIPT", "DISCOVERY") is None


def test_scaling_never_empties_a_pool_by_rounding() -> None:
    """Only an explicit 0.0 removes paper from a file; 0.1 just means 'less'."""
    assert scaled_count(1, 0.1) == 1
    assert scaled_count(4, 0.5) == 2
    assert scaled_count(4, 2.5) == 10
    assert scaled_count(3, 0.0) == 0
    assert scaled_count(0, 4.0) == 0


def test_characteristic_side_is_the_higher_weight() -> None:
    assert EmissionProfile(1.0, 3.0).characteristic_side() == "defense"
    assert EmissionProfile(1.0, 0.0).characteristic_side() == "applicant"
    assert EmissionProfile(1.0, 1.0).characteristic_side() is None


# ---------------------------------------------------------------------------
# ISC-78 — applicant-only paper is absent from a defense file
# ---------------------------------------------------------------------------


@requires_substrate
def test_applicant_only_paper_is_absent_from_a_defense_file(
    defense_seed: CaseSeed,
) -> None:
    """ISC-78: defense counsel runs no intake and writes no advocacy letters."""
    applicant_plan = build_case_plan(_mirror(defense_seed, "applicant"))
    defense_subtypes = {doc.subtype for doc in build_case_plan(defense_seed).documents}
    applicant_subtypes = {doc.subtype for doc in applicant_plan.documents}

    present_on_applicant = applicant_subtypes & set(APPLICANT_ONLY_SUBTYPES)
    assert present_on_applicant, "the probe seed must produce applicant-only paper"
    assert not (defense_subtypes & set(APPLICANT_ONLY_SUBTYPES))


@requires_substrate
def test_an_explicit_override_forces_applicant_only_paper_back_with_a_warning(
    defense_seed: CaseSeed,
) -> None:
    """ISC-79: perspective is a default, not a veto — the ISC-29 path still wins.

    And it must say *why* it is overruling: "suppressed by the defense
    perspective", not the misleading "the lifecycle never emits it".
    """
    forced = _mirror(
        defense_seed,
        "defense",
        documents={
            **defense_seed.documents.model_dump(exclude_none=True),
            "overrides": [{"subtype": "CLIENT_INTAKE_CORRESPONDENCE", "count": 2}],
        },
    )
    plan = build_case_plan(forced)

    counts = Counter(doc.subtype for doc in plan.documents)
    assert counts["CLIENT_INTAKE_CORRESPONDENCE"] == 2

    warning = next(
        (w for w in plan.warnings if "CLIENT_INTAKE_CORRESPONDENCE" in w), None
    )
    assert warning is not None, plan.warnings
    assert "perspective" in warning
    assert "override wins" in warning


def test_suppression_reasons_reach_the_control_resolver() -> None:
    """The seam itself, in isolation: pre_dropped only changes the *explanation*."""
    resolution = resolve_document_controls(
        [DocumentCandidate(subtype="OTHER_DOC")],
        _controls(overrides=[{"subtype": "CLIENT_STATUS_LETTERS", "count": 1}]),
        pre_dropped={"CLIENT_STATUS_LETTERS": "defense perspective (applicant-only)"},
    )
    assert resolution.count_for("CLIENT_STATUS_LETTERS") == 1
    assert any("defense perspective" in w for w in resolution.warnings)


# ---------------------------------------------------------------------------
# ISC-80 — comparative frequency
# ---------------------------------------------------------------------------


@requires_substrate
def test_defense_files_carry_materially_more_carrier_and_investigation_paper(
    defense_seed: CaseSeed,
) -> None:
    """ISC-80: mirrored seeds, and the defense side is strictly heavier."""
    applicant_plan = build_case_plan(_mirror(defense_seed, "applicant"))
    defense_plan = build_case_plan(defense_seed)

    def weight(plan: Any) -> int:
        return sum(
            1
            for doc in plan.documents
            if doc.parent_type in {"CLAIMS_ADMINISTRATION", "INVESTIGATION"}
        )

    assert weight(defense_plan) > weight(applicant_plan)


@requires_substrate
def test_a_defense_file_always_has_investigation_paper(defense_seed: CaseSeed) -> None:
    """The floor: no multiple of zero is ever more than zero."""
    defense_plan = build_case_plan(defense_seed)
    investigation = [
        doc for doc in defense_plan.documents if doc.parent_type == "INVESTIGATION"
    ]
    assert investigation, "a defense file without surveillance is not a defense file"


@requires_substrate
def test_the_investigation_floor_outranks_routine_correspondence_under_a_cap(
    defense_seed: CaseSeed,
) -> None:
    """Regression — the demo caseload caught this one emitting *zero*.

    Planted as trimmable supporting paper, the floor was the first thing
    ``global_cap`` deleted, so the one mechanism whose entire job is "a defense
    file always has surveillance" reliably produced a defense file with none.

    The claim under test is a *relative* one: while a cap is still trimming
    routine correspondence, it must not have reached the floor. It is not that
    the floor is untouchable — squeeze a 71-document case into 30 and the cap
    runs out of correspondence entirely and starts cutting dispositive paper,
    at which point losing the surveillance is correct. So this asserts the
    floor survives alongside the routine paper it outranks.
    """
    capped = _mirror(defense_seed, "defense", documents={"global_cap": 40})
    plan = build_case_plan(capped)

    assert plan.document_count == 40
    assert [doc for doc in plan.documents if doc.parent_type == "INVESTIGATION"]
    # The cap was still eating ordinary correspondence when it stopped, which is
    # what makes the survival above meaningful rather than incidental.
    assert any(
        entry.priority > FLOOR_PRIORITY for entry in plan.control.planned
    ), "cap trimmed past routine paper; pick a looser cap for this probe"


@requires_substrate
def test_settlement_demand_survives_on_both_sides_with_the_author_unchanged(
    defense_seed: CaseSeed,
) -> None:
    """Applicant-authored on both files; only the direction of travel differs."""
    applicant_docs = build_case_plan(_mirror(defense_seed, "applicant")).documents
    defense_docs = build_case_plan(defense_seed).documents

    def demand(docs: Any) -> Any:
        return next(
            (d for d in docs if d.subtype == "SETTLEMENT_DEMAND_LETTER"), None
        )

    applicant_demand = demand(applicant_docs)
    defense_demand = demand(defense_docs)
    assert applicant_demand is not None
    assert defense_demand is not None
    assert applicant_demand.author_role == ROLE_APPLICANT_ATTORNEY
    assert defense_demand.author_role == ROLE_APPLICANT_ATTORNEY
    # Outgoing on one file, received on the other.
    assert applicant_demand.recipient_role == ROLE_DEFENSE_ATTORNEY
    assert defense_demand.recipient_role == ROLE_DEFENSE_ATTORNEY


# ---------------------------------------------------------------------------
# ISC-81 — roles
# ---------------------------------------------------------------------------


def test_client_correspondence_flips_author_and_recipient() -> None:
    """'Client' is the worker on one file and the employer/carrier on the other."""
    applicant = document_roles(
        "CLIENT_CORRESPONDENCE_INFORMATIONAL", ROLE_APPLICANT_ATTORNEY, "applicant"
    )
    defense = document_roles(
        "CLIENT_CORRESPONDENCE_INFORMATIONAL", ROLE_APPLICANT_ATTORNEY, "defense"
    )
    assert applicant.author_role == ROLE_APPLICANT_ATTORNEY
    assert applicant.recipient_role == ROLE_INJURED_WORKER
    assert defense.author_role == ROLE_DEFENSE_ATTORNEY
    assert defense.recipient_role == ROLE_EMPLOYER


def test_facts_keep_their_natural_author_on_both_files() -> None:
    """An order is the judge's on a defense file too. Flipping it would be wrong."""
    for perspective in ("applicant", "defense"):
        roles = document_roles("ORDER_APPROVING_SETTLEMENT", ROLE_COURT, perspective)
        assert roles.author_role == ROLE_COURT


def test_received_paper_is_addressed_to_the_file_owner() -> None:
    roles = document_roles("ANSWER_TO_APPLICATION", ROLE_DEFENSE_ATTORNEY, "applicant")
    assert roles.author_role == ROLE_DEFENSE_ATTORNEY
    assert roles.recipient_role == ROLE_APPLICANT_ATTORNEY


def test_file_owner_firm_follows_the_perspective() -> None:
    assert file_owner_firm("applicant", "Martinez & Associates", "Grancell") == (
        "Martinez & Associates"
    )
    assert file_owner_firm("defense", "Martinez & Associates", "Grancell") == "Grancell"


# ---------------------------------------------------------------------------
# ISC-82 — the mirrored-facts invariant
# ---------------------------------------------------------------------------


@requires_substrate
def test_mirrored_seeds_produce_identical_case_facts(defense_seed: CaseSeed) -> None:
    """ISC-82: perspective changes the file. It must not change the case.

    Same cast (both firms exist in both files), same ADJ number, same injury and
    lifecycle dates. This is the invariant the whole feature rests on.
    """
    applicant_plan = build_case_plan(_mirror(defense_seed, "applicant"))
    defense_plan = build_case_plan(defense_seed)

    assert applicant_plan.cast.manifest_fields() == defense_plan.cast.manifest_fields()
    assert applicant_plan.cast.adj_number == defense_plan.cast.adj_number
    assert applicant_plan.cast.treating_physician == defense_plan.cast.treating_physician
    assert applicant_plan.cast.qme_physician == defense_plan.cast.qme_physician
    assert applicant_plan.timeline == defense_plan.timeline


@requires_substrate
def test_both_firms_exist_in_both_casts(defense_seed: CaseSeed) -> None:
    """Opposing counsel does not vanish because you changed chairs."""
    for plan in (build_case_plan(_mirror(defense_seed, "applicant")),
                 build_case_plan(defense_seed)):
        assert plan.cast.applicant_firm
        assert plan.cast.defense_firm


@requires_substrate
def test_the_applicant_path_is_an_identity_function(defense_seed: CaseSeed) -> None:
    """Why every pre-perspective seed stays byte-stable: nothing happens at all.

    Not "produces the same result" — literally the same objects, in the same
    order, with no RNG drawn. An applicant file cannot drift because there is no
    code path for it to drift along.
    """
    seed = _mirror(defense_seed, "applicant")
    plan = build_case_plan(seed)
    candidates = list(plan.control.planned)
    assert candidates  # sanity

    from wc_caseload_engine.lifecycle_bridge import build_core_candidates, build_timeline

    timeline = build_timeline(seed)
    core = build_core_candidates(seed, timeline)
    result = apply_perspective(seed, timeline, core)
    assert list(result.candidates) == core
    assert result.suppressed == {}
    assert result.notes == ()


# ---------------------------------------------------------------------------
# ISC-83 — manifests carry the perspective
# ---------------------------------------------------------------------------


@requires_substrate
def test_case_and_caseload_manifests_record_the_perspective(
    tmp_path: Path, defense_seed: CaseSeed
) -> None:
    """ISC-83: a generated file states whose file it is, without re-reading the seed."""
    from wc_caseload_engine.manifests import generate_caseload

    applicant_seed = _mirror(defense_seed, "applicant", case_id="mirror-applicant")
    generate_caseload("pov-probe", [applicant_seed, defense_seed], tmp_path)

    applicant_manifest = json.loads(
        (tmp_path / "mirror-applicant" / "manifest.json").read_text()
    )
    defense_manifest = json.loads(
        (tmp_path / defense_seed.case_id / "manifest.json").read_text()
    )
    assert applicant_manifest["perspective"] == "applicant"
    assert defense_manifest["perspective"] == "defense"

    caseload = json.loads((tmp_path / "caseload_manifest.json").read_text())
    assert caseload["perspectiveCounts"] == {"applicant": 1, "defense": 1}
    assert {case["perspective"] for case in caseload["cases"]} == {
        "applicant",
        "defense",
    }


@requires_substrate
def test_a_defense_manifest_is_still_valid_classifier_ground_truth(
    tmp_path: Path, defense_seed: CaseSeed
) -> None:
    """ISC-84: swapped and planted subtypes are canonical keys, or nothing is."""
    from wc_caseload_engine.manifests import generate_caseload, validate_output_tree

    generate_caseload("pov-probe", [defense_seed], tmp_path)
    report = validate_output_tree(tmp_path)
    assert report.ok, report.render()


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def defense_seed() -> CaseSeed:
    """A defense file rich enough to exercise every mechanism.

    Resolved C&R with a QME: produces work product to swap, client intake and
    advocacy paper to suppress, claims administration to scale up, and a
    settlement demand to re-address.
    """
    return parse_case_seed(
        {
            "case_id": "pov-probe",
            "rng_seed": 777001,
            "perspective": "defense",
            "profile": {
                "applicant": {"name": "Dana Whitaker", "age": 41},
                "attorneys": {"defense_firm": "Grancell, Stander & Kinsey"},
            },
            "injury": {
                "type": "specific",
                "date_of_injury": "2022-06-21",
                "body_parts": [{"part": "lumbar_spine", "icd10": "M54.5"}],
            },
            "lifecycle": {
                "target_stage": "resolved",
                "claim_response": "accepted",
                "eval_type": "qme",
                "resolution": {"type": "c_and_r"},
            },
        }
    )


def _mirror(seed: CaseSeed, perspective: str, **overrides: Any) -> CaseSeed:
    """The same seed seen from the other chair (and nothing else changed)."""
    payload = seed.model_dump(mode="json", exclude_none=True)
    payload["perspective"] = perspective
    payload.update(overrides)
    return parse_case_seed(payload)


def _controls(**kwargs: Any) -> Any:
    from wc_caseload_engine.seeds import DocumentControls

    return DocumentControls.model_validate(kwargs)
