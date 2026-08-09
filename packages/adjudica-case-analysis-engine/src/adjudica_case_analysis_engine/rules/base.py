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
    """The path of the record a scalar hangs off.

    Mapping keys containing path-structural characters are escaped upstream, so
    splitting on the final separator can never cut a key in half.
    """
    head, separator, _ = source_path.rpartition(".")
    return head if separator else source_path


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
        """Index a ledger for rule execution."""
        ordered = tuple(facts)
        vocabulary = {fact.id: tokens(f"{fact.field} {fact.source_path}") for fact in ordered}
        record_keys = {
            fact.id: (source_of(fact), parent_path(fact.source_path)) for fact in ordered
        }
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
