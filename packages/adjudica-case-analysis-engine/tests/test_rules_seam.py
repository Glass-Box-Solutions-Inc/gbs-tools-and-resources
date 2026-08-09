"""The rule-pack seam — what detector class #2 may rely on without a refactor.

These tests pin the seam's contract rather than any one detector's judgement, so
they stay meaningful when the registry grows.
"""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from adjudica_case_analysis_engine.analysis import analyze_paths, review_facts
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
