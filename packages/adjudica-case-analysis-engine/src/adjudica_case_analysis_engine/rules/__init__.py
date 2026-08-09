"""Registered consistency rule packs.

Adding detector class #2 is a sibling module exporting a :class:`Rule`, plus one more
entry in :data:`RULES`. Nothing here needs to change, and no existing pack is touched.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from adjudica_case_analysis_engine.models import Fact, Finding
from adjudica_case_analysis_engine.rules import anatomical_coherence
from adjudica_case_analysis_engine.rules.base import Rule, RuleContext, source_of

#: Every detector class the engine runs, in registration order.
RULES: tuple[Rule, ...] = (anatomical_coherence.RULE,)

__all__ = ["RULES", "Rule", "RuleContext", "run_rules", "source_of"]


def _validate_registry(rules: Sequence[Rule]) -> None:
    """Check that every pack owns a unique name and a code set no other pack claims.

    Declaring a code is a claim of ownership, so two packs declaring one code leaves a
    finding unattributable — a scorecard cannot say which detector class produced it,
    and the per-pack check in :func:`run_rules` would wave it through from either side.
    """
    names: set[str] = set()
    owner: dict[str, str] = {}
    for rule in rules:
        if rule.name in names:
            raise ValueError(
                f"duplicate rule name {rule.name!r}; each detector class needs a unique key"
            )
        names.add(rule.name)
        for code in sorted(rule.codes):
            if code in owner:
                raise ValueError(
                    f"finding code {code!r} is declared by both {owner[code]!r} and "
                    f"{rule.name!r}; a code belongs to exactly one detector class"
                )
            owner[code] = rule.name


def run_rules(facts: Iterable[Fact], *, rules: Sequence[Rule] | None = None) -> tuple[Finding, ...]:
    """Run every registered pack over one ledger, returning findings in report order.

    A pack may only emit codes it declared. Detection is scored per detector class, so
    an undeclared code would belong to no class at all and would quietly skew the
    scorecard rather than fail — that is a defect in the pack, and it stops here.
    """
    selected = RULES if rules is None else rules
    _validate_registry(selected)
    context = RuleContext.from_facts(facts)
    findings: list[Finding] = []
    for rule in selected:
        for finding in rule.detect(context):
            if finding.code not in rule.codes:
                raise ValueError(
                    f"rule {rule.name!r} emitted undeclared finding code {finding.code!r}; "
                    f"declared codes are {sorted(rule.codes)}"
                )
            findings.append(finding)
    return tuple(sorted(findings, key=lambda item: (item.severity, item.code, item.fact_ids)))
