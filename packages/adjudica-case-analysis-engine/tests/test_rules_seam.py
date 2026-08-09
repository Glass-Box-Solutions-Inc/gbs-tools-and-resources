"""The rule-pack seam — what detector class #2 may rely on without a refactor.

These tests pin the seam's contract rather than any one detector's judgement, so
they stay meaningful when the registry grows.
"""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from adjudica_case_analysis_engine.analysis import analyze_facts, analyze_paths, review_facts
from adjudica_case_analysis_engine.cli import cli
from adjudica_case_analysis_engine.input import normalize_paths
from adjudica_case_analysis_engine.models import Finding
from adjudica_case_analysis_engine.rules import RULES, Rule, RuleContext, run_rules

FIXTURES = Path(__file__).parent / "fixtures"


def _facts(tmp_path: Path, name: str, payload: object):
    source = tmp_path / name
    source.write_text(json.dumps(payload), encoding="utf-8")
    return normalize_paths([source])


def test_every_registered_pack_names_itself_and_declares_its_codes() -> None:
    """A scorecard buckets findings per detector class, so every class needs a unique key."""
    assert RULES, "the registry must hold at least the anatomical coherence pack"
    names = [rule.name for rule in RULES]
    assert len(names) == len(set(names))
    for rule in RULES:
        assert rule.name and rule.name.islower()
        assert rule.codes, f"{rule.name} declares no finding codes"
        assert all(code.islower() for code in rule.codes)

    # A code belongs to exactly one class, or a scorecard cannot attribute it.
    claimed: set[str] = set()
    for rule in RULES:
        assert not claimed & rule.codes, f"{rule.name} re-declares an owned code"
        claimed |= rule.codes


def test_two_packs_may_not_declare_the_same_finding_code() -> None:
    """Ownership is what makes a code attributable, so a collision fails before execution."""

    def detect(context: RuleContext):
        return ()

    first = Rule(name="first", codes=frozenset({"shared_code"}), detect=detect)
    second = Rule(name="second", codes=frozenset({"shared_code"}), detect=detect)

    with pytest.raises(ValueError, match="shared_code"):
        run_rules((), rules=(first, second))


def test_two_packs_may_not_share_a_name() -> None:
    """The class key is the scorecard's bucket; two packs sharing one would merge scores."""

    def detect(context: RuleContext):
        return ()

    first = Rule(name="duplicated", codes=frozenset({"a_code"}), detect=detect)
    second = Rule(name="duplicated", codes=frozenset({"b_code"}), detect=detect)

    with pytest.raises(ValueError, match="duplicated"):
        run_rules((), rules=(first, second))


def test_a_pack_may_not_emit_a_code_it_never_declared(tmp_path: Path) -> None:
    """An undeclared code would land in no detector class at all — that fails loudly."""

    def detect(context: RuleContext):
        yield Finding(code="smuggled_code", severity="info", message="x", category="medical")

    rogue = Rule(name="rogue", codes=frozenset({"declared_code"}), detect=detect)
    facts = _facts(tmp_path, "case.json", {"anything": 1})

    with pytest.raises(ValueError, match="undeclared finding code"):
        run_rules(facts, rules=(rogue,))


def test_a_pack_may_see_a_divergence_and_stay_silent(tmp_path: Path) -> None:
    """Reporting is the pack's decision, never the seam's; silence is a first-class outcome."""

    def detect(context: RuleContext):
        assert context.facts  # the pack saw the ledger and chose not to report
        return ()

    quiet = Rule(name="quiet", codes=frozenset({"unused_code"}), detect=detect)
    facts = _facts(tmp_path, "case.json", {"anything": 1})

    assert run_rules(facts, rules=(quiet,)) == ()


def test_registering_another_pack_is_an_append(tmp_path: Path) -> None:
    """Detector class #2 adds a module and one tuple entry; it never edits class #1."""

    def detect(context: RuleContext):
        yield Finding(code="second_pack", severity="info", message="second", category="medical")

    extra = Rule(name="second", codes=frozenset({"second_pack"}), detect=detect)
    facts = normalize_paths([FIXTURES / "anatomy_intake_wrist.json"])

    registered = run_rules(facts)
    combined = run_rules(facts, rules=(*RULES, extra))

    assert set(registered).issubset(set(combined))
    assert any(finding.code == "second_pack" for finding in combined)


def test_the_context_hands_back_the_record_a_fact_belongs_to(tmp_path: Path) -> None:
    """A pack reads a sibling field instead of re-deriving the path grammar itself."""
    facts = _facts(
        tmp_path,
        "case.json",
        {"surgery": {"cptCode": "29827", "uncoded": False}, "other": {"cptCode": "27447"}},
    )
    context = RuleContext.from_facts(facts)
    code_fact = next(fact for fact in facts if fact.source_path == "$.surgery.cptCode")

    siblings = {fact.field for fact in context.record_of(code_fact)}
    assert siblings == {"cptCode", "uncoded"}
    assert context.source_of(code_fact) == "case.json"


def test_each_promoted_claim_is_its_own_record(tmp_path: Path) -> None:
    """Claims in one list are separate assertions, not siblings of each other.

    Grouping them at the dotted parent puts every claim in the file into one record,
    so an unrelated claim's flag would speak for all of them.
    """
    facts = _facts(
        tmp_path,
        "claims.json",
        {
            "claims": [
                {"field": "surgery_cpt_code", "value": "29827"},
                {"field": "uncoded", "value": True},
            ]
        },
    )
    context = RuleContext.from_facts(facts)
    code_fact = next(fact for fact in facts if fact.field == "surgery_cpt_code")

    assert [fact.field for fact in context.record_of(code_fact)] == ["surgery_cpt_code"]


def test_scalar_fields_inside_a_mapping_record_still_group(tmp_path: Path) -> None:
    """The list fix must not break the grouping the detector relies on."""
    facts = _facts(
        tmp_path,
        "case.json",
        {"surgeries": [{"cptCode": "29827", "uncoded": True}, {"cptCode": "27447"}]},
    )
    context = RuleContext.from_facts(facts)

    first = next(fact for fact in facts if fact.source_path == "$.surgeries[0].cptCode")
    assert {fact.field for fact in context.record_of(first)} == {"cptCode", "uncoded"}

    second = next(fact for fact in facts if fact.source_path == "$.surgeries[1].cptCode")
    assert {fact.field for fact in context.record_of(second)} == {"cptCode"}


def test_terminal_scalar_list_elements_are_not_one_record(tmp_path: Path) -> None:
    """body_parts[0] and body_parts[1] are separate values, not a shared record."""
    facts = _facts(tmp_path, "case.json", {"injury": {"body_parts": ["wrist", "knee"]}})
    context = RuleContext.from_facts(facts)

    first = next(fact for fact in facts if fact.source_path == "$.injury.body_parts[0]")
    assert len(context.record_of(first)) == 1


def test_an_empty_ledger_runs_every_pack_and_reports_nothing() -> None:
    """No facts is a valid case, not an error path."""
    assert run_rules(()) == ()
    assert RuleContext.from_facts(()).facts == ()


def test_hostile_values_cannot_crash_a_registered_pack(tmp_path: Path) -> None:
    """Phase 2's exit criterion: hostile input neither raises nor is silently dropped."""
    facts = _facts(
        tmp_path,
        "hostile.json",
        {
            "caseFacts": {
                "surgery": {
                    "cptCode": ["29827", {"nested": "29827"}],
                    "cptDescription": "  ✂ 29827 ",
                    "uncoded": "maybe",
                    "count": 10**40,
                }
            },
            "injury": {"body_part": ["", None, {"deep": "wrist"}], "note": "🩻"},
            "$weird.key[0]": "29827",
        },
    )

    findings = run_rules(facts)
    assert all(isinstance(finding, Finding) for finding in findings)
    # Nothing was silently dropped on the way in: the awkward shapes are still facts.
    paths = {fact.source_path for fact in facts}
    assert "$.injury.body_part[2].deep" in paths
    assert any(path.startswith("$.~4weird") for path in paths)


def test_analysis_reports_carry_rule_pack_findings_alongside_integrity_findings() -> None:
    """The pack is wired into the report, and the report stays sorted and deterministic."""
    report = analyze_paths(
        [FIXTURES / "anatomy_intake_wrist.json", FIXTURES / "anatomy_manifest_shoulder.json"]
    )

    assert any(finding.code == "anatomical_contradiction" for finding in report.findings)
    assert any(finding.code == "limited_evidence" for finding in report.findings)

    ordering = [(finding.severity, finding.code, finding.fact_ids) for finding in report.findings]
    assert ordering == sorted(ordering), "rule-pack findings must merge into the report's order"
    assert report.domains["medical"]["findingIds"].count("anatomical_contradiction") == 1


def test_the_gate_and_the_report_cannot_disagree_about_a_contradiction() -> None:
    """One definition feeds both surfaces, so a pack finding cannot reach only one of them.

    A detector that emits a Finding nobody gates on is a detector that catches nothing.
    """
    inputs = [FIXTURES / "anatomy_intake_wrist.json", FIXTURES / "anatomy_manifest_shoulder.json"]
    shared = review_facts(normalize_paths(inputs))

    assert any(finding.code == "anatomical_contradiction" for finding in shared)

    # Surface one: the analysis report.
    report = analyze_paths(inputs)
    assert set(shared).issubset(set(report.findings))

    # Surface two: the gate-facing exit code, which is what a corpus check runs.
    result = CliRunner().invoke(cli, ["validate", *(str(path) for path in inputs)])
    assert result.exit_code == 1
    assert json.loads(result.output)["findings"] == [finding.as_dict() for finding in shared]


def test_the_finding_contract_never_depends_on_caller_order(tmp_path: Path) -> None:
    """Both surfaces canonicalize the ledger once, so factIds cannot diverge.

    `analyze_facts` re-sorts facts by (category, field, id) while CLI normalization
    sorts by value — so a rule accumulating citations in ledger order emitted the same
    finding with differently ordered factIds depending on which surface asked.
    """
    bodies = {
        "forward.json": {
            "injury": {"body_parts": ["right wrist", "left wrist"]},
            "caseFacts": {"surgery": {"status": "performed", "cptCode": "29827"}},
        },
        "reverse.json": {
            "caseFacts": {"surgery": {"status": "performed", "cptCode": "29827"}},
            "injury": {"body_parts": ["right wrist", "left wrist"]},
        },
    }
    for name, body in bodies.items():
        source = tmp_path / name
        source.write_text(json.dumps(body), encoding="utf-8")
        facts = normalize_paths([source])

        shared = [item for item in review_facts(facts) if item.code == "anatomical_contradiction"]
        assert len(shared) == 1, name
        # Citations are sorted, so no rule can make contract bytes ledger-order-dependent.
        assert shared[0].fact_ids[1:] == tuple(sorted(shared[0].fact_ids[1:])), name

        from_report = [
            item
            for item in analyze_facts(facts).findings
            if item.code == "anatomical_contradiction"
        ]
        result = CliRunner().invoke(cli, ["validate", str(source)])
        from_cli = [
            item
            for item in json.loads(result.output)["findings"]
            if item["code"] == "anatomical_contradiction"
        ]

        assert from_report == shared, name
        assert from_cli == [item.as_dict() for item in shared], name
