"""The consistency rule-pack seam: registered detector classes over one shared ledger.

:func:`~adjudica_case_analysis_engine.validation.validate_facts` checks the ledger
against *itself* — provenance, confidence, contradictory values, chronology. A rule
pack is the other half: a named detector class that reads the same ledger through
domain knowledge the ledger does not carry, and reports only what that knowledge
affirmatively contradicts.

Three properties are deliberate, because detector classes 2..n are already named
(laterality, diagnostic modality against body part, benefit gap against delay notice,
and a contention-quality pack) and each must be an append rather than a refactor.

**A pack names itself and declares its codes.** Detection is scored per detector
class, and ``Finding.category`` is already spoken for as a report domain key — it is
inherited from the offending fact for conflicts, so it cannot also identify a
detector. ``Rule.name`` is the class key and ``Rule.codes`` is the closed set of
codes that class may emit. :func:`~adjudica_case_analysis_engine.rules.run_rules`
refuses anything else, so a code can never drift out of the class that owns it.

**A pack decides whether a divergence is reportable.** The seam collects findings; it
never infers one from a comparison it performed itself. A detector that sees a
divergence and stays silent on purpose is a first-class outcome — a later pack has to
separate legitimate divergence from internal incoherence, and would be unable to if
this layer treated every mismatch as a finding.

**A pack sees structure, not only a flat list.** :meth:`RuleContext.record_of` returns
the record a fact hangs off, so a detector can read a sibling field — ``surgery.uncoded``
here, a document's interim/final status later — instead of re-deriving the path grammar
in every pack.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from adjudica_case_analysis_engine.models import Fact, Finding
from adjudica_case_analysis_engine.text import tokens


def source_of(fact: Fact) -> str:
    """The input label a fact was normalized from.

    ``Fact.id`` is ``"{label}:{sourcePath}"``, so the label is recovered by length
    rather than by splitting — a fallback label such as ``input-0:manifest.json``
    contains a colon of its own.
    """
    suffix = f":{fact.source_path}"
    return fact.id[: -len(suffix)] if fact.id.endswith(suffix) else fact.id


def parent_path(source_path: str) -> str:
    """The path of the mapping a scalar hangs off.

    Mapping keys containing path-structural characters are escaped upstream, so
    splitting on the final separator can never cut a key in half.
    """
    head, separator, _ = source_path.rpartition(".")
    return head if separator else source_path


def canonical_order(facts: Iterable[Fact]) -> tuple[Fact, ...]:
    """One ledger order for every consumer, whatever order the caller assembled.

    Lives at the seam because it is a promise to *packs*: a detector accumulating
    citations as it walks the ledger must produce the same bytes whether it was reached
    through a report, which sorts facts by domain, or through the CLI, which sorts them
    by value.
    """
    return tuple(sorted(facts, key=lambda item: (item.category, item.field, item.id)))


def record_key(fact: Fact) -> tuple[str, str]:
    """The record a fact belongs to: its input label, plus that record's path.

    A promoted claim names its own field and is a self-contained assertion, and a
    terminal scalar list element is a value in its own right — each is its own record.
    Grouping either at the dotted parent would collapse every claim in a file, or every
    element of one list, into a single record, letting an unrelated entry's flag speak
    for all of them: one ``{"field": "uncoded", "value": true}`` claim would suppress
    every other claim's operation.

    A scalar field inside a mapping record keeps its parent, so ``surgeries[0].cptCode``
    still sees ``surgeries[0].uncoded`` — which is the grouping detectors rely on.
    """
    if fact.scope == "claim" or fact.source_path.endswith("]"):
        return (source_of(fact), fact.source_path)
    return (source_of(fact), parent_path(fact.source_path))


@dataclass(frozen=True, slots=True)
class RuleContext:
    """A read-only view of one case's ledger, indexed the ways detectors ask for it.

    Built once per analysis and shared by every pack, so vocabulary and record
    grouping are derived a single time rather than once per detector.
    """

    #: Every normalized fact, in the order the ledger supplied them.
    facts: tuple[Fact, ...]
    #: Fact id -> the field/path vocabulary that fact is recognized by.
    vocabulary: Mapping[str, frozenset[str]]
    #: (input label, parent path) -> every fact of that record.
    records: Mapping[tuple[str, str], tuple[Fact, ...]]
    #: Fact id -> the record key above.
    record_keys: Mapping[str, tuple[str, str]]

    @classmethod
    def from_facts(cls, facts: Iterable[Fact]) -> RuleContext:
        """Index a ledger for rule execution, in one canonical order."""
        ordered = canonical_order(facts)
        vocabulary = {fact.id: tokens(f"{fact.field} {fact.source_path}") for fact in ordered}
        record_keys = {fact.id: record_key(fact) for fact in ordered}
        grouped: dict[tuple[str, str], list[Fact]] = defaultdict(list)
        for fact in ordered:
            grouped[record_keys[fact.id]].append(fact)
        return cls(
            ordered,
            MappingProxyType(vocabulary),
            MappingProxyType({key: tuple(value) for key, value in grouped.items()}),
            MappingProxyType(record_keys),
        )

    def words(self, fact: Fact) -> frozenset[str]:
        """The field/path vocabulary of one fact, or an empty set for a stranger."""
        return self.vocabulary.get(fact.id, frozenset())

    def matching(self, markers: Collection[str]) -> tuple[Fact, ...]:
        """Facts whose field/path vocabulary names any of ``markers``, in ledger order."""
        wanted = frozenset(markers)
        return tuple(fact for fact in self.facts if self.words(fact) & wanted)

    def record_of(self, fact: Fact) -> tuple[Fact, ...]:
        """Every fact sharing this fact's input and immediate parent — its sibling record."""
        key = self.record_keys.get(fact.id)
        return self.records.get(key, ()) if key is not None else ()

    def source_of(self, fact: Fact) -> str:
        """The input label this fact came from."""
        return source_of(fact)


@dataclass(frozen=True, slots=True)
class Rule:
    """One registered detector class.

    ``name`` is the key a scorecard buckets by; ``codes`` is every finding code this
    class may emit; ``detect`` is the detector itself.
    """

    name: str
    codes: frozenset[str]
    detect: Callable[[RuleContext], Iterable[Finding]]
