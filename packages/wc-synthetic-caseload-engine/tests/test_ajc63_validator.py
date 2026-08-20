"""AJC-63/M4 frozen validator, quality-contract, and export oracles."""

from __future__ import annotations

import copy
import datetime as dt
import json
import shutil
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from click.testing import CliRunner

from test_medical_assertions import (
    _assertion,
    _contention,
    _context,
    _ledger,
    _opinion,
    _world,
)
from wc_caseload_engine.cli import cli
from wc_caseload_engine.manifests import (
    build_manifest,
    generate_caseload,
    validate_output_tree,
)
from wc_caseload_engine.medical_assertions import (
    MedicalAssertionLedger,
    apportionment_quality,
    assertion_context,
    contention_quality,
    escobedo_misses,
    grade_ledger,
    opinion_quality,
    project_medical_history,
    validate_medical_assertions,
)
from wc_caseload_engine.renderer import MIME_TYPES, RenderResult
from wc_caseload_engine.seeds import (
    load_caseload_spec,
    parse_case_seed,
    resolve_caseload,
)
from wc_caseload_engine.truth_manifest import (
    ALWAYS_PRESENT_V2_KEYS,
    TRUTH_DIR,
    TruthManifestError,
    assertion_ledger_digest,
    build_case_truth_manifest,
    build_caseload_truth_manifest,
    medical_assertions_from_truth,
    parse_medical_assertions_from_truth,
)


def _base(*, examined: bool = True, author: str = "qme"):
    return _opinion(
        "opn-01",
        author_role=author,
        report_date=dt.date(2023, 2, 1),
        examination_performed=examined,
    )


def _response(
    opinion_id: str = "opn-02",
    *,
    predecessor: str = "opn-01",
    author: str = "qme",
    report_date: dt.date = dt.date(2023, 9, 1),
    event_kind: str = "supplemental_report",
):
    return _opinion(
        opinion_id,
        author_role=author,
        report_date=report_date,
        event_kind=event_kind,
        revision_kind="unchanged_additional_reasoning",
        responds_to_opinion_id=predecessor,
        examination_performed=False,
        revision_rationale="the additional testimony confirms the prior allocation",
    )


def _response_ledger(
    opinions: tuple,
    *,
    owner: str = "opn-02",
) -> tuple[MedicalAssertionLedger, object]:
    assertion = _assertion(opinion_id=owner)
    return _ledger(opinions=opinions, assertions=(assertion,)), assertion


def _direct_grades(
    ledger: MedicalAssertionLedger,
    assertion: object,
    contract: str,
) -> tuple[tuple[str, ...], str, str]:
    return (
        escobedo_misses(
            _world(), ledger, assertion, quality_contract=contract  # type: ignore[arg-type]
        ),
        apportionment_quality(
            _world(),
            _context(),
            ledger,
            assertion,  # type: ignore[arg-type]
            quality_contract=contract,  # type: ignore[arg-type]
        ),
        opinion_quality(
            _world(),
            _context(),
            ledger,
            ledger.opinion(assertion.opinion_id),  # type: ignore[union-attr]
            quality_contract=contract,  # type: ignore[arg-type]
        ),
    )


BOUND_DOCUMENT_INDEXES = [0, 2, 5]


def _bound_plan() -> Any:
    """A literal three-position binding fixture over the §2 response chain."""
    from test_truth_manifest import _m4_response_plan

    plan = _m4_response_plan("assertions-m4-bound")
    ledger = plan.medical_assertions
    assert ledger is not None
    ctn_01 = _contention(
        "ctn-01",
        target_condition_id="cond-00",
        rationale="the lumbar condition followed the industrial injury",
    )
    ctn_02 = _contention(
        "ctn-02",
        party="defense",
        position="deny",
        target_condition_id="cond-00",
        rationale="the lumbar condition predated the industrial injury",
    )
    opinion_delta = {
        "concurs_with_contention_ids": ("ctn-01",),
        "defers_contention_ids": ("ctn-02",),
        "aoe_coe_finding": "industrial",
        "aoe_coe_rationale": "the records support both industrial and prior causes",
    }
    base = ledger.medical_opinions[0].model_copy(update=opinion_delta)
    response = ledger.medical_opinions[1].model_copy(update=opinion_delta)
    ledger = MedicalAssertionLedger(
        contentions=(ctn_01, ctn_02),
        medical_opinions=(base, response),
        apportionment_assertions=ledger.apportionment_assertions,
    )
    documents = list(plan.documents)
    documents[0] = replace(
        documents[0],
        subtype="ADVOCACY_LETTERS_QME",
        template_subtype="INTERNAL_TEMPLATE_MUST_NOT_EXPORT",
        target_medical_opinion_id="opn-01",
        contention_surface="advocacy",
        contention_actor_party="applicant",
    )
    documents[2] = replace(
        documents[2],
        subtype="ADVOCACY_LETTERS_PTP_QME_AME",
        template_subtype="OBJECTION_TO_QME_AME_REPORT",
        target_medical_opinion_id="opn-02",
        spoken_contention_ids=("ctn-01", "ctn-02"),
        contention_surface="objection",
        contention_actor_party="defense",
        defense_contest_theories=("insufficient_investigation",),
    )
    documents[5] = replace(
        documents[5],
        subtype="DEPOSITION_TRANSCRIPT",
        template_subtype="QME_DEPOSITION_TRANSCRIPT",
        medical_opinion_id="opn-02",
        target_medical_opinion_id="opn-01",
        spoken_contention_ids=("ctn-01",),
        contention_surface="qme_deposition",
    )
    return replace(plan, documents=tuple(documents), medical_assertions=ledger)


def _assert_no_nulls(value: Any) -> None:
    if isinstance(value, dict):
        assert all(item is not None for item in value.values())
        for item in value.values():
            _assert_no_nulls(item)
    elif isinstance(value, list):
        for item in value:
            _assert_no_nulls(item)


def _manifest_for_plan(plan: Any, tmp_path: Path) -> dict[str, Any]:
    renders = []
    for document in plan.documents:
        result = RenderResult(
            path=tmp_path / f"{document.index}.fake",
            subtype=document.subtype,
            doc_format=document.doc_format,
            doc_date=document.doc_date,
            size=1,
            md5=f"{document.index:032x}",
            mime_type=MIME_TYPES[document.doc_format],
            template="FrozenFixture",
        )
        renders.append((f"{document.index}.fake", result))
    return build_manifest(plan, renders)


@pytest.fixture(scope="module")
def v2_validator_tree(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One real v2 output tree shared by all polarity plants."""
    from test_truth_manifest import _ASSERTION_SCENARIO, _seed_body

    body = _seed_body(
        "ajc63-v2-divergence",
        scenario=copy.deepcopy(_ASSERTION_SCENARIO),
        rng_seed=6363,
    )
    out_dir = tmp_path_factory.mktemp("ajc63-v2-validator")
    generate_caseload(
        "ajc63-v2-validator",
        (parse_case_seed(body),),
        out_dir,
        truth=True,
        truth_manifest_version=2,
    )
    return out_dir


def _copied_tree(source: Path, tmp_path: Path) -> Path:
    destination = tmp_path / "out"
    shutil.copytree(source, destination)
    return destination


def _case_truth_path(out_dir: Path) -> Path:
    return out_dir / TRUTH_DIR / "ajc63-v2-divergence.truth.json"


def _write_truth(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


CLEAN_V2_CORPUS_PATHS = (
    Path(__file__).parent / "fixtures" / "medical_story_leakage_probe.yaml",
    Path(__file__).parents[1] / "examples" / "medical-story-showcase.yaml",
    Path(__file__).parent / "fixtures" / "ajc63_divergence.yaml",
)


@pytest.fixture(scope="module")
def clean_v2_corpora(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[tuple[Path, tuple[Any, ...]], ...]:
    generated: list[tuple[Path, tuple[Any, ...]]] = []
    for spec_path in CLEAN_V2_CORPUS_PATHS:
        spec = load_caseload_spec(spec_path)
        out_dir = tmp_path_factory.mktemp(f"ajc63-clean-{spec.caseload_id}")
        results = generate_caseload(
            spec.caseload_id,
            resolve_caseload(spec),
            out_dir,
            truth=True,
            truth_manifest_version=2,
        )
        generated.append((out_dir, results))
    return tuple(generated)


def test_v2_response_chain_incorporates_examined_base_without_changing_v1() -> None:
    """A2-R7 direct-call witness: only v2 incorporates predecessor examination."""
    ledger, assertion = _response_ledger((_base(), _response()))

    assert _direct_grades(ledger, assertion, "1.0.0") == (("5a",), "thin", "thin")
    assert _direct_grades(ledger, assertion, "2.0.0") == ((), "supported", "supported")
    graded = grade_ledger(
        _context(), _world(), ledger, quality_contract="2.0.0"
    )
    assert graded.apportionment_assertions[0].quality == "supported"
    assert graded.opinion("opn-02").quality == "supported"

    supplemental = _response(report_date=dt.date(2023, 7, 1))
    deposition = _response(
        "opn-03",
        predecessor="opn-02",
        report_date=dt.date(2023, 10, 1),
        event_kind="deposition",
    )
    two_hop, two_hop_row = _response_ledger(
        (_base(), supplemental, deposition), owner="opn-03"
    )
    assert _direct_grades(two_hop, two_hop_row, "2.0.0") == (
        (),
        "supported",
        "supported",
    )


def test_assertions_v2_item_5a_inherits_only_a_same_author_examined_predecessor_chain() -> None:
    """Malformed chains miss 5a directly; coherence remains a separate gate."""
    empty_response = _response().model_copy(
        update={"responds_to_opinion_id": None}
    )
    empty_row = _assertion(opinion_id="opn-02")
    empty = MedicalAssertionLedger.model_construct(
        contentions=(),
        medical_opinions=(empty_response,),
        apportionment_assertions=(empty_row,),
    )
    unexamined, unexamined_row = _response_ledger(
        (_base(examined=False), _response())
    )
    missing, missing_row = _response_ledger(
        (_response(predecessor="opn-77"),)
    )
    wrong_author, wrong_author_row = _response_ledger(
        (_base(author="ame"), _response(author="qme"))
    )
    nonbackward, nonbackward_row = _response_ledger(
        (
            _base(),
            _response(report_date=dt.date(2023, 1, 1)),
        )
    )
    same_date_base = _base().model_copy(update={"report_date": dt.date(2023, 1, 1)})
    same_date, same_date_row = _response_ledger(
        (
            same_date_base,
            _response(report_date=dt.date(2023, 1, 1)),
        )
    )
    first = _response(
        "opn-01",
        predecessor="opn-02",
        report_date=dt.date(2023, 7, 1),
    )
    second = _response(
        "opn-02",
        predecessor="opn-01",
        report_date=dt.date(2023, 8, 1),
    )
    cycle, cycle_row = _response_ledger((first, second))

    for ledger, row in (
        (empty, empty_row),
        (unexamined, unexamined_row),
        (missing, missing_row),
        (wrong_author, wrong_author_row),
        (nonbackward, nonbackward_row),
        (same_date, same_date_row),
        (cycle, cycle_row),
    ):
        misses, assertion_grade, _opinion_grade = _direct_grades(
            ledger, row, "2.0.0"
        )
        assert "5a" in misses
        assert assertion_grade == "thin"

    assert (
        "medical opinion 'opn-02' responds to unknown opinion 'opn-77'"
        in validate_medical_assertions(_context(), _world(), missing)
    )
    assert any(
        "keeps its predecessor's author" in problem
        for problem in validate_medical_assertions(_context(), _world(), wrong_author)
    )
    assert any(
        "response and supersession targets must be strictly earlier" in problem
        for problem in validate_medical_assertions(_context(), _world(), nonbackward)
    )
    assert any(
        "response and supersession targets must be strictly earlier" in problem
        for problem in validate_medical_assertions(_context(), _world(), same_date)
    )
    assert any(
        "medical opinion chain contains a cycle" in problem
        for problem in validate_medical_assertions(_context(), _world(), cycle)
    )


def test_assertions_v2_schema_is_exact_additive_delta_over_v1() -> None:
    """The 2.x schema is a literal additive projection, never a model dump."""
    from pydantic import BaseModel

    from test_truth_manifest import (
        AJC61_APPORTIONMENT_ASSERTION_FIELDS,
        AJC61_CASE_CHANNEL_KEYS,
        AJC61_CASELOAD_CASE_KEYS,
        AJC61_CASELOAD_CHANNEL_KEYS,
        AJC61_CONDITION_FIELDS,
        AJC61_CONTENTION_FIELDS,
        AJC61_MEDICAL_OPINION_FIELDS,
    )
    from wc_caseload_engine import truth_manifest as tm

    class ExpansionControl(BaseModel):
        id: str
        internal_only: str

    expected_case_keys = (
        *AJC61_CASE_CHANNEL_KEYS[:-1],
        "contentionDocuments",
        "ledgerDigest",
    )
    expected_condition_fields = (*AJC61_CONDITION_FIELDS, "psych_injury_kind")
    expected_contention_fields = (
        *AJC61_CONTENTION_FIELDS[:-1],
        "psych_injury_kind",
        "quality",
    )
    expected_opinion_fields = (
        *AJC61_MEDICAL_OPINION_FIELDS[:-1],
        "event_kind",
        "revision_kind",
        "concurs_with_contention_ids",
        "defers_contention_ids",
        "psych_injury_kind",
        "aoe_coe_finding",
        "aoe_coe_rationale",
        "quality",
    )
    expected_binding_fields = (
        "document_index",
        "subtype",
        "document_date",
        "spoken_contention_ids",
        "medical_opinion_id",
        "target_medical_opinion_id",
        "contention_surface",
        "contention_actor_party",
        "defense_contest_theories",
    )
    expected_rollup_case_keys = (*AJC61_CASELOAD_CASE_KEYS, "contentionDocumentCount")

    assert frozenset(
        {"contentionDocuments", "spokenContentionIds"}
    ) == ALWAYS_PRESENT_V2_KEYS
    assert expected_case_keys == tm.ASSERTIONS_V2_CASE_CHANNEL_KEYS
    assert expected_condition_fields == tm.ASSERTIONS_V2_CONDITION_FIELDS
    assert expected_contention_fields == tm.ASSERTIONS_V2_CONTENTION_FIELDS
    assert expected_opinion_fields == tm.ASSERTIONS_V2_MEDICAL_OPINION_FIELDS
    assert (
        tm.ASSERTIONS_V2_APPORTIONMENT_ASSERTION_FIELDS
        == AJC61_APPORTIONMENT_ASSERTION_FIELDS
    )
    assert expected_binding_fields == tm.ASSERTIONS_V2_CONTENTION_DOCUMENT_FIELDS
    assert tm.ASSERTIONS_V2_CASELOAD_CHANNEL_KEYS == AJC61_CASELOAD_CHANNEL_KEYS
    assert expected_rollup_case_keys == tm.ASSERTIONS_V2_CASELOAD_CASE_KEYS
    assert tm._assertions_v2_projection(
        ExpansionControl(id="control", internal_only="must-not-export"),
        ("id",),
    ) == {"id": "control"}

    from test_truth_manifest import _m4_response_plan

    empty_plan = _m4_response_plan("assertions-m4-empty-bindings")
    empty_v2 = build_case_truth_manifest(empty_plan, truth_manifest_version=2)
    assert empty_v2["schemaVersion"] == "1.0.0"
    assert tm.MONEY_CHANNEL_VERSION == "1.1.0"
    empty_channel = empty_v2["channels"]["assertions"]
    assert tuple(empty_channel) == expected_case_keys
    assert empty_channel["contentionDocuments"] == []

    plan = _bound_plan()
    default_v1 = build_case_truth_manifest(plan)
    explicit_v1 = build_case_truth_manifest(plan, truth_manifest_version=1)
    assert default_v1 == explicit_v1
    channel = build_case_truth_manifest(
        plan, truth_manifest_version=2
    )["channels"]["assertions"]
    assert tuple(channel) == expected_case_keys
    assert channel["contentionDocuments"] == [
        {
            "documentIndex": 0,
            "subtype": "ADVOCACY_LETTERS_QME",
            "documentDate": "2023-02-20",
            "spokenContentionIds": [],
            "targetMedicalOpinionId": "opn-01",
            "contentionSurface": "advocacy",
            "contentionActorParty": "applicant",
        },
        {
            "documentIndex": 2,
            "subtype": "ADVOCACY_LETTERS_PTP_QME_AME",
            "documentDate": "2023-08-11",
            "spokenContentionIds": ["ctn-01", "ctn-02"],
            "targetMedicalOpinionId": "opn-02",
            "contentionSurface": "objection",
            "contentionActorParty": "defense",
            "defenseContestTheories": ["insufficient_investigation"],
        },
        {
            "documentIndex": 5,
            "subtype": "DEPOSITION_TRANSCRIPT",
            "documentDate": "2023-12-12",
            "spokenContentionIds": ["ctn-01"],
            "medicalOpinionId": "opn-02",
            "targetMedicalOpinionId": "opn-01",
            "contentionSurface": "qme_deposition",
        },
    ]
    required_binding_keys = {
        "documentIndex",
        "subtype",
        "documentDate",
        "spokenContentionIds",
    }
    for row in channel["contentionDocuments"]:
        assert required_binding_keys <= set(row)
        assert set(row) <= {
            "documentIndex",
            "subtype",
            "documentDate",
            "spokenContentionIds",
            "medicalOpinionId",
            "targetMedicalOpinionId",
            "contentionSurface",
            "contentionActorParty",
            "defenseContestTheories",
        }
        assert "templateSubtype" not in row

    for opinion in channel["medicalOpinions"]:
        assert "eventKind" in opinion
        assert ("revisionKind" in opinion) is (opinion["eventKind"] != "base_report")
    assert "doctrineHooks" not in channel["contentions"][0]
    _assert_no_nulls(channel)
    parsed = medical_assertions_from_truth(
        build_case_truth_manifest(plan, truth_manifest_version=2)
    )
    assert parsed is not None


def test_v2_contention_document_export_is_lossless_manifest_linked_and_digest_bound() -> None:
    """Final bindings are lossless, canonical, digest-bound, and ID-checked."""
    plan = _bound_plan()
    payload = build_case_truth_manifest(plan, truth_manifest_version=2)
    channel = payload["channels"]["assertions"]
    expected = [
        {
            "documentIndex": 0,
            "subtype": "ADVOCACY_LETTERS_QME",
            "documentDate": "2023-02-20",
            "spokenContentionIds": [],
            "targetMedicalOpinionId": "opn-01",
            "contentionSurface": "advocacy",
            "contentionActorParty": "applicant",
        },
        {
            "documentIndex": 2,
            "subtype": "ADVOCACY_LETTERS_PTP_QME_AME",
            "documentDate": "2023-08-11",
            "spokenContentionIds": ["ctn-01", "ctn-02"],
            "targetMedicalOpinionId": "opn-02",
            "contentionSurface": "objection",
            "contentionActorParty": "defense",
            "defenseContestTheories": ["insufficient_investigation"],
        },
        {
            "documentIndex": 5,
            "subtype": "DEPOSITION_TRANSCRIPT",
            "documentDate": "2023-12-12",
            "spokenContentionIds": ["ctn-01"],
            "medicalOpinionId": "opn-02",
            "targetMedicalOpinionId": "opn-01",
            "contentionSurface": "qme_deposition",
        },
    ]
    assert channel["contentionDocuments"] == expected
    original_digest = channel["ledgerDigest"]

    changed = copy.deepcopy(payload)
    changed_channel = changed["channels"]["assertions"]
    changed_channel["contentionDocuments"][0]["spokenContentionIds"] = ["ctn-01"]
    changed_channel["ledgerDigest"] = assertion_ledger_digest(changed_channel)
    assert changed_channel["ledgerDigest"] != original_digest

    dangling = copy.deepcopy(payload)
    dangling_channel = dangling["channels"]["assertions"]
    dangling_channel["contentionDocuments"][1]["spokenContentionIds"] = ["ctn-77"]
    dangling_channel["ledgerDigest"] = assertion_ledger_digest(dangling_channel)
    with pytest.raises(TruthManifestError, match="unknown contention 'ctn-77'"):
        medical_assertions_from_truth(dangling)

    dangling_medical = copy.deepcopy(payload)
    dangling_medical_channel = dangling_medical["channels"]["assertions"]
    dangling_medical_channel["contentionDocuments"][2]["medicalOpinionId"] = "opn-77"
    dangling_medical_channel["ledgerDigest"] = assertion_ledger_digest(
        dangling_medical_channel
    )
    with pytest.raises(
        TruthManifestError,
        match=(
            "contentionDocuments documentIndex 5 medicalOpinionId references "
            "unknown medical opinion 'opn-77'"
        ),
    ):
        medical_assertions_from_truth(dangling_medical)

    dangling_target = copy.deepcopy(payload)
    dangling_target_channel = dangling_target["channels"]["assertions"]
    dangling_target_channel["contentionDocuments"][0]["targetMedicalOpinionId"] = "opn-77"
    dangling_target_channel["ledgerDigest"] = assertion_ledger_digest(dangling_target_channel)
    with pytest.raises(
        TruthManifestError,
        match=(
            "contentionDocuments documentIndex 0 targetMedicalOpinionId "
            "references unknown medical opinion 'opn-77'"
        ),
    ):
        medical_assertions_from_truth(dangling_target)

    impossible = copy.deepcopy(payload)
    impossible_channel = impossible["channels"]["assertions"]
    impossible_channel["contentionDocuments"][0]["subtype"] = "APPLICATION_FOR_ADJUDICATION"
    impossible_channel["ledgerDigest"] = assertion_ledger_digest(impossible_channel)
    with pytest.raises(TruthManifestError, match="cannot carry contentionSurface 'advocacy'"):
        medical_assertions_from_truth(impossible)

    documents = list(plan.documents)
    documents[0], documents[1] = (
        replace(documents[1], index=0),
        replace(documents[0], index=1),
    )
    reordered_plan = replace(plan, documents=tuple(documents))
    reordered = build_case_truth_manifest(
        reordered_plan, truth_manifest_version=2
    )["channels"]["assertions"]["contentionDocuments"]
    assert reordered[0]["documentIndex"] == 1
    assert {key: value for key, value in reordered[0].items() if key != "documentIndex"} == {
        key: value for key, value in expected[0].items() if key != "documentIndex"
    }
    assert reordered[1:] == expected[1:]


def test_manifest_document_positions_equal_planned_document_indexes_by_construction(
    tmp_path: Path,
) -> None:
    """The three frozen positions link plan, manifest, and v2 projection both ways."""
    plan = _bound_plan()
    manifest = _manifest_for_plan(plan, tmp_path)
    bindings = build_case_truth_manifest(
        plan, truth_manifest_version=2
    )["channels"]["assertions"]["contentionDocuments"]
    by_index = {row["documentIndex"]: row for row in bindings}
    assert set(by_index) == set(BOUND_DOCUMENT_INDEXES)

    for literal_index in BOUND_DOCUMENT_INDEXES:
        assert plan.documents[literal_index].index == literal_index
    assert manifest["documents"][0]["subtype"] == plan.documents[0].subtype
    assert manifest["documents"][0]["documentDate"] == "2023-02-20"
    assert manifest["documents"][2]["subtype"] == plan.documents[2].subtype
    assert manifest["documents"][2]["documentDate"] == "2023-08-11"
    assert manifest["documents"][5]["subtype"] == plan.documents[5].subtype
    assert manifest["documents"][5]["documentDate"] == "2023-12-12"
    assert by_index[0]["subtype"] == manifest["documents"][0]["subtype"]
    assert by_index[0]["documentDate"] == manifest["documents"][0]["documentDate"]
    assert by_index[2]["subtype"] == manifest["documents"][2]["subtype"]
    assert by_index[2]["documentDate"] == manifest["documents"][2]["documentDate"]
    assert by_index[5]["subtype"] == manifest["documents"][5]["subtype"]
    assert by_index[5]["documentDate"] == manifest["documents"][5]["documentDate"]


def test_v2_caseload_rollup_adds_only_binding_counts(tmp_path: Path) -> None:
    from test_truth_manifest import AJC61_CASELOAD_CASE_KEYS, AJC61_CASELOAD_CHANNEL_KEYS

    plan = _bound_plan()
    result = SimpleNamespace(
        case_id=plan.seed.case_id,
        plan=plan,
        truth_path=tmp_path / TRUTH_DIR / f"{plan.seed.case_id}.truth.json",
    )
    rollup = build_caseload_truth_manifest(
        "ajc63-v2-rollup", (result,), truth_manifest_version=2
    )
    channel = rollup["channels"]["assertions"]
    assert tuple(channel) == AJC61_CASELOAD_CHANNEL_KEYS
    assert channel["channelVersion"] == "2.0.0"
    assert channel["counts"] == {
        "contentions": 2,
        "medicalOpinions": 2,
        "apportionmentAssertions": 2,
        "contentionDocuments": 3,
    }
    assert tuple(channel["cases"][0]) == (
        *AJC61_CASELOAD_CASE_KEYS,
        "contentionDocumentCount",
    )
    assert channel["cases"][0]["contentionDocumentCount"] == 3


def test_quality_contract_is_required_keyword_only_on_all_five_entry_points() -> None:
    import inspect

    functions = (
        contention_quality,
        escobedo_misses,
        apportionment_quality,
        opinion_quality,
        grade_ledger,
    )
    for function in functions:
        parameter = inspect.signature(function).parameters["quality_contract"]
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
        assert parameter.default is inspect.Parameter.empty


def test_contention_document_binding_docstring_preserves_the_export_boundary() -> None:
    from wc_caseload_engine.medical_assertions import ContentionDocumentBinding

    text = ContentionDocumentBinding.__doc__ or ""
    assert "assertions truth channel ``2.x``" in text
    assert "never carries\n    ``quality`` or a quality-like field" in text
    assert "never enters the ordinary manifest" in text
    assert "never enters seed YAML" in text
    assert "Never exported" not in text
    assert "no truth channel" not in text


def test_hidden_condition_is_owner_local_5b_divergence_not_incoherence() -> None:
    from test_medical_assertions import _condition

    world = _world(conditions=(_condition(surfaces_in_file=False),))
    opinion = _opinion(reviewed_condition_ids=("cond-01",))
    assertion = _assertion()
    ledger = _ledger(opinions=(opinion,), assertions=(assertion,))
    assert validate_medical_assertions(_context(), world, ledger) == ()
    assert (
        escobedo_misses(world, ledger, assertion, quality_contract="1.0.0")
        == ("5b",)
    )
    assert (
        escobedo_misses(world, ledger, assertion, quality_contract="2.0.0")
        == ("5b",)
    )


def test_validate_out_v2_accepts_planted_world_truth_divergence(
    v2_validator_tree: Path,
) -> None:
    """A resolved nonindustrial-vs-industrial assertion is graded, never rejected."""
    payload = json.loads(_case_truth_path(v2_validator_tree).read_text(encoding="utf-8"))
    channel = payload["channels"]["assertions"]
    condition = next(
        row for row in channel["medicalHistory"]["conditions"] if row["id"] == "cond-00"
    )
    contention = next(row for row in channel["contentions"] if row["id"] == "ctn-01")
    assert condition["causalGroundTruth"] == "nonindustrial"
    assert condition["surfacesInFile"] is True
    assert contention["targetConditionId"] == "cond-00"
    assert contention["position"] == "affirm"
    assert contention["quality"] == "unsupportable"

    report = validate_output_tree(v2_validator_tree)
    assert report.problems == []
    result = CliRunner().invoke(cli, ["validate", "--out", str(v2_validator_tree)])
    assert result.exit_code == 0


def test_validate_out_v2_rejects_planted_internal_incoherence(
    v2_validator_tree: Path,
    tmp_path: Path,
) -> None:
    out_dir = _copied_tree(v2_validator_tree, tmp_path)
    truth_path = _case_truth_path(out_dir)
    payload = json.loads(truth_path.read_text(encoding="utf-8"))
    channel = payload["channels"]["assertions"]
    contention = next(row for row in channel["contentions"] if row["id"] == "ctn-01")
    contention["targetConditionId"] = "cond-77"
    channel["ledgerDigest"] = assertion_ledger_digest(channel)
    _write_truth(truth_path, payload)

    report = validate_output_tree(out_dir)
    wrapper_prefix = (
        f"ajc63-v2-divergence: truth manifest {truth_path} cannot be validated ("
    )
    assert len(report.problems) == 1
    assert report.problems[0].startswith(wrapper_prefix)
    assert (
        "contention 'ctn-01' references unknown condition 'cond-77'"
        in report.problems[0]
    )
    result = CliRunner().invoke(cli, ["validate", "--out", str(out_dir)])
    assert result.exit_code == 1


def test_validate_out_v2_rejects_tampered_quality_after_digest_recomputed(
    v2_validator_tree: Path,
    tmp_path: Path,
) -> None:
    out_dir = _copied_tree(v2_validator_tree, tmp_path)
    truth_path = _case_truth_path(out_dir)
    payload = json.loads(truth_path.read_text(encoding="utf-8"))
    channel = payload["channels"]["assertions"]
    contention = next(row for row in channel["contentions"] if row["id"] == "ctn-01")
    assert contention["quality"] == "unsupportable"
    contention["quality"] = "supported"
    channel["ledgerDigest"] = assertion_ledger_digest(channel)
    _write_truth(truth_path, payload)

    report = validate_output_tree(out_dir)
    wrapper_prefix = (
        f"ajc63-v2-divergence: truth manifest {truth_path} cannot be validated ("
    )
    assert len(report.problems) == 1
    assert report.problems[0].startswith(wrapper_prefix)
    assert (
        "channels.assertions: quality 'supported' on 'ctn-01' does not match "
        "the rederived grade 'unsupportable'"
        in report.problems[0]
    )
    result = CliRunner().invoke(cli, ["validate", "--out", str(out_dir)])
    assert result.exit_code == 1


def test_validate_out_v2_does_not_reach_the_substrate(
    v2_validator_tree: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import wc_caseload_engine.substrate as substrate

    def forbidden(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("v2 truth validation reached the substrate")

    monkeypatch.setattr(substrate, "import_substrate", forbidden)
    assert validate_output_tree(v2_validator_tree).problems == []


@pytest.mark.slow
def test_validate_out_v2_has_zero_false_positives_on_clean_medical_story_corpus(
    clean_v2_corpora: tuple[tuple[Path, tuple[Any, ...]], ...],
    tmp_path: Path,
) -> None:
    """Three frozen corpora round-trip clean; a same-corpus dangling plant fails once."""
    qualities: set[str] = set()
    for out_dir, results in clean_v2_corpora:
        assert validate_output_tree(out_dir).problems == []
        for result in results:
            truth_path = out_dir / TRUTH_DIR / f"{result.case_id}.truth.json"
            payload = json.loads(truth_path.read_text(encoding="utf-8"))
            channel = payload["channels"]["assertions"]
            assert channel["channelVersion"] == "2.0.0"
            qualities.update(row["quality"] for row in channel["contentions"])
            qualities.update(row["quality"] for row in channel["medicalOpinions"])
            qualities.update(
                row["quality"] for row in channel["apportionmentAssertions"]
            )

            parsed = parse_medical_assertions_from_truth(payload)
            assert parsed is not None
            _contract, parsed_context, parsed_projection, parsed_ledger, _bindings = (
                parsed
            )
            plan_context = assertion_context(result.plan.seed, result.plan.timeline)
            plan_projection = project_medical_history(
                result.plan.medical_history,
                plan_context.current_body_parts,
            )
            in_memory_problems = validate_medical_assertions(
                plan_context,
                plan_projection,
                result.plan.medical_assertions,
            )
            parsed_problems = validate_medical_assertions(
                parsed_context,
                parsed_projection,
                parsed_ledger,
            )
            assert parsed_problems == in_memory_problems
    assert qualities == {"supported", "thin", "unsupportable"}

    divergence_out, divergence_results = clean_v2_corpora[2]
    copied = _copied_tree(divergence_out, tmp_path)
    source_result = divergence_results[0]
    source_ledger = source_result.plan.medical_assertions
    assert source_ledger is not None
    mutated_contention = source_ledger.contentions[0].model_copy(
        update={"target_condition_id": "cond-77"}
    )
    mutated_ledger = MedicalAssertionLedger(
        contentions=(mutated_contention, *source_ledger.contentions[1:]),
        medical_opinions=source_ledger.medical_opinions,
        apportionment_assertions=source_ledger.apportionment_assertions,
    )
    memory_context = assertion_context(
        source_result.plan.seed, source_result.plan.timeline
    )
    memory_projection = project_medical_history(
        source_result.plan.medical_history,
        memory_context.current_body_parts,
    )
    in_memory_problems = validate_medical_assertions(
        memory_context, memory_projection, mutated_ledger
    )

    truth_path = copied / TRUTH_DIR / "ajc63-divergence-visible.truth.json"
    payload = json.loads(truth_path.read_text(encoding="utf-8"))
    channel = payload["channels"]["assertions"]
    channel["contentions"][0]["targetConditionId"] = "cond-77"
    channel["ledgerDigest"] = assertion_ledger_digest(channel)
    _write_truth(truth_path, payload)
    parsed = parse_medical_assertions_from_truth(payload)
    assert parsed is not None
    parsed_problems = validate_medical_assertions(parsed[1], parsed[2], parsed[3])
    literal_problem = "contention 'ctn-01' references unknown condition 'cond-77'"
    assert in_memory_problems == (literal_problem,)
    assert parsed_problems == in_memory_problems

    report = validate_output_tree(copied)
    wrapper_prefix = (
        f"ajc63-divergence-visible: truth manifest {truth_path} cannot be validated ("
    )
    assert len(report.problems) == 1
    assert report.problems[0].startswith(wrapper_prefix)
    assert literal_problem in report.problems[0]
    other_rule_texts = (
        "percentages sum to",
        "medical opinion chain contains a cycle",
        "references unknown medical opinion",
        "does not match the rederived grade",
        "cannot carry contentionSurface",
    )
    assert all(text not in report.problems[0] for text in other_rule_texts)


def test_ajc63_keeps_package_version_at_0_9_0() -> None:
    import tomllib

    from wc_caseload_engine import __version__

    package_root = Path(__file__).parents[1]
    declared = tomllib.loads(
        (package_root / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]["version"]
    provenance = build_case_truth_manifest(
        _bound_plan(), truth_manifest_version=2
    )["provenance"]["generator"]
    assert __version__ == "0.9.0"
    assert declared == "0.9.0"
    assert provenance == "wc-synthetic-caseload-engine@0.9.0"


def test_ajc63_default_and_feature_absent_outputs_are_byte_identical_to_post_ajc62(
    tmp_path: Path,
) -> None:
    import hashlib

    from test_truth_manifest import _ASSERTION_SCENARIO, _seed_body
    from wc_caseload_engine.planner import build_case_plan

    def tree_digests(root: Path, *, include_truth: bool) -> dict[str, str]:
        return {
            path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*"))
            if path.is_file()
            and (include_truth or path.relative_to(root).parts[0] != TRUTH_DIR)
        }

    body = _seed_body(
        "ajc63-byte-identity",
        scenario=copy.deepcopy(_ASSERTION_SCENARIO),
        rng_seed=6364,
    )
    seed = parse_case_seed(body)
    v1_out = tmp_path / "v1"
    v2_out = tmp_path / "v2"
    generate_caseload("ajc63-byte-identity", (seed,), v1_out, truth=True)
    generate_caseload(
        "ajc63-byte-identity",
        (seed,),
        v2_out,
        truth=True,
        truth_manifest_version=2,
    )
    assert tree_digests(v1_out, include_truth=False) == tree_digests(
        v2_out, include_truth=False
    )
    assert tree_digests(v1_out, include_truth=True) != tree_digests(
        v2_out, include_truth=True
    )
    v1_truth = json.loads(
        (v1_out / TRUTH_DIR / "ajc63-byte-identity.truth.json").read_text(
            encoding="utf-8"
        )
    )
    assert v1_truth["channels"]["assertions"]["channelVersion"] == "1.0.0"

    history_only = _seed_body(
        "ajc63-feature-absent",
        scenario={"medical_history": {"sample_conditions": False}},
        rng_seed=6365,
    )
    absent_truth = build_case_truth_manifest(
        build_case_plan(parse_case_seed(history_only), case_number=1),
        truth_manifest_version=2,
    )
    assert "assertions" not in absent_truth["channels"]

    expected_golden_hashes = {
        "demo-caseload.json": "f56160aa08dd6e6660a593b4d2e463c6a630c24277f5a6a6135b48ac41dd0e66",
        "doctrine-showcase.json": (
            "11c0b95f5f4659112eaff4a04acc6eba96b6c63647f99d270c1e83dcaeb03df9"
        ),
        "medical-story-showcase.json": (
            "60dff418398a4849eb3023f418e2deecc0d04f03ee8ed5b738309886dc2ed639"
        ),
        # AJC-64 item 0d (M5-R30): the settlement deduction rows now carry the
        # ENGINE_POLICY_UNCONFIRMED label, which moves rendered bytes on every
        # compromise and release in this corpus. Superseding R109's
        # a8db048b3ad7…ecda2ea, admitted as its own literal digest so the
        # re-record stays a reviewable decision rather than a silent refreeze.
        # The item's own allowlist proof is what establishes this is a LABEL
        # change: `facts` and `seed` did not move on any case.
        # Round-1 finding F2 extended that labelling to the prose duplicates in
        # the signed documents, superseding 866022279cb6…d02b2b78. Still a
        # label-only move: facts and seed did not drift on any case.
        "money-showcase.json": "540571c2689d3fa031aaf4065660439f39a3dab2d3cc20e5cccca4c7953e633a",
        "personas-showcase.json": (
            "f89280b194ef08877b81a9876e38c9752e8460ad3cd5d7441cd4e156c4dd8275"
        ),
    }
    golden_dir = Path(__file__).parent / "golden"
    assert {path.name for path in golden_dir.glob("*.json")} == {
        *expected_golden_hashes,
        "money-w2-showcase.json",
    }
    assert {
        name: hashlib.sha256((golden_dir / name).read_bytes()).hexdigest()
        for name in expected_golden_hashes
    } == expected_golden_hashes
