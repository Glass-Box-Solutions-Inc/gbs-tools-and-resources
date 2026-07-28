"""Doctrine content — the landmark authorities, as renderable language.

``lifecycle.doctrine_hooks`` names the doctrines a case turns on. Before this
module those names reached the manifest, forced the psych flag and nudged
complexity, and stopped there: a caseload seeded ``[kite, escobedo]`` rendered
documents that never said "Kite" or "Escobedo" anywhere. A classifier corpus
built from it could not be used to measure whether a model finds doctrine
language, because the language was not in the corpus.

This module is the content table that closes that gap. Each of the fourteen
:data:`~wc_caseload_engine.seeds.DoctrineHook` values maps to one
:class:`DoctrineContent`: the controlling authority, a short **marker** that
survives PDF text extraction, and two pools of paragraphs — one written in the
register of a med-legal evaluator's discussion addendum, one in the register of
points and authorities in a brief. Which pool a document draws from is decided
by the document's own subtype, through :attr:`DoctrineContent.medical_targets`
and :attr:`DoctrineContent.legal_targets`.

Three properties are load-bearing:

* **Every target key is canonical.** A target that is not one of the
  classifier's 353 subtypes would silently never match, and the hook would
  quietly render nothing — the exact failure this module exists to end.
  ``tests/test_doctrine_content.py`` asserts the whole target surface against
  :func:`~wc_caseload_engine.taxonomy.effective_taxonomy`.
* **Every paragraph carries its hook's marker.** The marker is what a probe (or
  a corpus consumer) greps for, so a paragraph without one is content that
  cannot be verified to have arrived.
* **A subtype has one register across all fourteen hooks.** ``TRIAL_BRIEF`` is
  legal for every hook that targets it; ``QME_COMPREHENSIVE_REPORT`` is medical
  for every hook that targets it. That invariant is what lets a document flagged
  with two hooks carry one heading instead of two contradictory ones.

**Real names.** The engine's standing rule is that no real person or
organization reaches output; :mod:`wc_caseload_engine.name_denylist` enforces it.
Case citations are the one deliberate exception — a controlling authority is
named by its case name or it is not a citation. The names admitted here are
therefore exactly the parties to published California decisions, and nothing
else. They are checked against the denylist and against the substrate's live
organization pools by ``tests/test_doctrine_content.py``, and they carry one
real hazard worth naming: a citation surname that also happens to be a seeded
applicant's surname would read as cross-case contamination in a generated
corpus. ``Ramirez`` is already both (see ``examples/demo-caseload.yaml``), which
is why the cross-case sweep in ``tests/test_coherence.py`` is the tripwire for
anyone adding a hook to a case whose neighbours share a citation's name.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import structlog

log = structlog.get_logger(__name__)

MEDICAL_REGISTER = "medical"
"""Register of a QME/AME/PTP discussion addendum."""

LEGAL_REGISTER = "legal"
"""Register of points and authorities in a brief, petition or denial."""

MEDICAL_HEADING = "ADDENDUM — MEDICAL-LEGAL DISCUSSION OF CONTROLLING AUTHORITY"
"""Section heading used on documents whose subtype is a medical target."""

LEGAL_HEADING = "POINTS AND AUTHORITIES — CONTROLLING DOCTRINE"
"""Section heading used on documents whose subtype is a legal target."""


@dataclass(frozen=True, slots=True)
class DoctrineFacts:
    """The case facts a doctrine prerequisite is allowed to consult.

    Deliberately a small, flat record rather than the seed itself. It is built
    both from a finished :class:`~wc_caseload_engine.seeds.CaseSeed` and, during
    ``auto:`` derivation, from lifecycle fields that exist before any seed does
    — and keeping it seed-shaped rather than seed-typed is what lets this module
    stay free of an import cycle with :mod:`wc_caseload_engine.seeds`.
    """

    injury_type: str
    body_part_count: int
    has_psych_body_part: bool
    eval_type: str
    claim_response: str
    imr_filed: bool
    seeded_hooks: frozenset[str] = frozenset()
    occupation: str = ""
    industry: str = ""

    @classmethod
    def from_seed(cls, seed: Any) -> DoctrineFacts:
        """Read the facts off a :class:`~wc_caseload_engine.seeds.CaseSeed`."""
        lifecycle = seed.lifecycle
        parts = seed.injury.body_parts
        return cls(
            injury_type=seed.injury.type,
            body_part_count=len(parts),
            has_psych_body_part=any(part.part == "psyche" for part in parts),
            eval_type=lifecycle.eval_type,
            claim_response=lifecycle.claim_response,
            imr_filed=bool(lifecycle.ur_dispute.enabled and lifecycle.ur_dispute.imr),
            seeded_hooks=frozenset(lifecycle.doctrine_hooks),
            occupation=seed.profile.applicant.occupation or "",
            industry=seed.profile.employer.industry or "",
        )


def _as_facts(subject: Any) -> DoctrineFacts:
    """Accept either a seed or an already-built :class:`DoctrineFacts`."""
    return subject if isinstance(subject, DoctrineFacts) else DoctrineFacts.from_seed(subject)


@dataclass(frozen=True, slots=True)
class DoctrinePrerequisite:
    """What a case must be able to show before a doctrine belongs in it.

    A doctrine hook is not decoration: it puts an argument in the file. An
    argument about apportioning between two injuries in a file that models one
    injury is not a hard document to generate — it is a document that describes
    a case the generator did not produce, and a corpus of those teaches a
    classifier to associate the doctrine with facts that are not on the page.

    ``description`` is the sentence a warning quotes, so it is written for the
    seed author who has to act on it.
    """

    description: str
    predicate: Callable[[DoctrineFacts], bool]

    def satisfied_by(self, subject: Any) -> bool:
        """``True`` when *subject* (a seed or facts) can support the doctrine."""
        return self.predicate(_as_facts(subject))


def _needs_rating(facts: DoctrineFacts) -> bool:
    """A permanent-disability rating exists only after a med-legal evaluation."""
    return facts.eval_type != "none"


_RATING_PREREQUISITE = DoctrinePrerequisite(
    description=(
        "the case must reach a permanent disability rating, which requires "
        "lifecycle.eval_type to be qme, ame or ime rather than none"
    ),
    predicate=_needs_rating,
)

_CONTESTED_PREREQUISITE = DoctrinePrerequisite(
    description=(
        "a threshold defence to compensability presupposes a contested claim — "
        "lifecycle.claim_response must be denied or delayed"
    ),
    predicate=lambda facts: facts.claim_response in {"denied", "delayed"},
)

_BENSON_PREREQUISITE = DoctrinePrerequisite(
    description=(
        "apportioning between injuries needs a rating and more than one impaired "
        "region to argue about — lifecycle.eval_type must not be none and "
        "injury.body_parts must name at least two parts"
    ),
    predicate=lambda facts: _needs_rating(facts) and facts.body_part_count >= 2,
)
"""Benson, and the one prerequisite that had to be weakened to stay honest.

Benson is about two *injuries*, and a ``CaseSeed`` models exactly one
``InjurySpec``. A predicate demanding what the doctrine really needs would
therefore reject every case the engine can generate, which is a way of deleting
the hook rather than governing it. The seed *can* establish multiple impaired
regions, which is what makes a multi-injury contention arguable rather than
absurd — so that is what this asks for, and the paragraphs were rewritten to
raise the second injury as a contention rather than to assert it as a finding.
Modelling a second date of injury is the real fix and belongs in the seed schema.
"""

_KITE_PREREQUISITE = DoctrinePrerequisite(
    description=(
        "adding impairments instead of combining them needs two impairments to "
        "add — lifecycle.eval_type must not be none and injury.body_parts must "
        "name at least two parts"
    ),
    predicate=lambda facts: _needs_rating(facts) and facts.body_part_count >= 2,
)
"""Kite, gated on there being something to add.

Found while correcting the README claim that ``benson`` was the only
prerequisite weaker than its doctrine. It was not: ``kite`` asked only for a
rating, so a single-region case satisfied it and auto-derivation could draw an
argument about the synergistic effect of two impairments into a file with one.
That is the same defect as N1 in a different hook, and unlike Benson's second
*injury*, a second impaired region is something a seed can express — so this is
a real gate rather than a documented approximation.
"""

_DEATH_PREREQUISITE = DoctrinePrerequisite(
    description="death benefits require injury.type to be death",
    predicate=lambda facts: facts.injury_type == "death",
)

_PSYCH_CLAIM_PREREQUISITE = DoctrinePrerequisite(
    description=(
        "the section 3208.3 threshold presupposes a psychiatric injury claim — "
        "name psyche in injury.body_parts"
    ),
    predicate=lambda facts: facts.has_psych_body_part,
)
"""The psychiatric threshold, gated on an actual psychiatric claim.

This asked only that the claim not be a death claim, which every orthopedic case
satisfies — so auto-derivation could draw the hook onto a lumbar-only file as
*supported*, injecting "This psychiatric evaluation is framed by..." into an
ordinary QME with no warning. A satisfied prerequisite bypasses the
kept-and-warned path, so a too-weak gate is worse than no gate: it launders the
incoherence as approved.

Deliberately the same shape as :data:`_GFPA_PREREQUISITE`, minus the escape
hatch. ``gfpa`` accepts ``lc3208_3_psych`` alongside it as evidence of a
psychiatric claim; this hook *is* that evidence, so it has to come from the
injury itself.

The guarantee is that the hook cannot be **auto-drawn** onto a case with no
psychiatric claim — not that it cannot reach one. Seeding it explicitly on an
orthopedic case still works, still renders, and is still warned about: a
prerequisite governs the draw, which is the channel nobody chose, and never
overrules a seed author.
"""

_GFPA_PREREQUISITE = DoctrinePrerequisite(
    description=(
        "a defence to a psychiatric claim needs a psychiatric claim to defend "
        "against — name psyche in injury.body_parts, or seed lc3208_3_psych "
        "alongside it"
    ),
    predicate=lambda facts: facts.has_psych_body_part
    or "lc3208_3_psych" in facts.seeded_hooks,
)

_SAFETY_MEMBER_PREREQUISITE = DoctrinePrerequisite(
    description=(
        "the section 3212.1 presumption runs to firefighters and peace officers — "
        "profile.employer.industry must be government, or profile.applicant."
        "occupation must name a qualifying role"
    ),
    predicate=lambda facts: facts.industry.lower() == "government"
    or any(
        word in facts.occupation.lower()
        for word in ("fire", "police", "peace officer", "sheriff", "deputy")
    ),
)

_IMR_PREREQUISITE = DoctrinePrerequisite(
    description=(
        "a challenge to independent medical review presupposes one happened — "
        "lifecycle.ur_dispute.enabled and lifecycle.ur_dispute.imr must both be true"
    ),
    predicate=lambda facts: facts.imr_filed,
)


@dataclass(frozen=True, slots=True)
class DoctrineContent:
    """One doctrine hook's renderable content and the subtypes it reaches.

    ``marker`` is deliberately short and free of punctuation that a PDF text
    extractor might reflow — a statute number, or the surname a decision is
    known by. It is the string every paragraph in both pools contains and the
    string a verification probe looks for.
    """

    hook: str
    display: str
    marker: str
    citation: str
    medical_paragraphs: tuple[str, ...]
    legal_paragraphs: tuple[str, ...]
    medical_targets: frozenset[str]
    legal_targets: frozenset[str]
    requires: DoctrinePrerequisite | None = None
    """What the case must show for this doctrine to belong in it.

    ``None`` is a decision, not an omission: the doctrine fits any case the
    engine can generate. Auto-derivation never draws a hook whose prerequisite
    fails; an explicitly seeded one is kept and warned about, because the seed
    is the contract (ISC-29) and the engine's job is to be loud rather than
    silently disobedient.
    """

    @property
    def targets(self) -> frozenset[str]:
        """Every subtype this hook injects content into."""
        return self.medical_targets | self.legal_targets

    def register_for(self, subtype: str) -> str | None:
        """``"medical"``, ``"legal"`` or ``None`` when this hook skips *subtype*."""
        if subtype in self.medical_targets:
            return MEDICAL_REGISTER
        if subtype in self.legal_targets:
            return LEGAL_REGISTER
        return None

    def paragraphs_for(self, subtype: str) -> tuple[str, ...]:
        """The pool this hook draws from for *subtype* (empty when it skips it)."""
        register = self.register_for(subtype)
        if register == MEDICAL_REGISTER:
            return self.medical_paragraphs
        if register == LEGAL_REGISTER:
            return self.legal_paragraphs
        return ()

    def targets_subtype(self, subtype: str) -> bool:
        """``True`` when this hook has content for *subtype*."""
        return subtype in self.targets


# ---------------------------------------------------------------------------
# Shared target sets
#
# Named rather than repeated so that "the med-legal report family" means one
# thing across all fourteen hooks. A hook that wants a narrower reach declares
# its own set; a hook that wants the family uses the family.
# ---------------------------------------------------------------------------

_CORE_MEDLEGAL: frozenset[str] = frozenset(
    {
        "QME_COMPREHENSIVE_REPORT",
        "AME_COMPREHENSIVE_REPORT",
        "SUPPLEMENTAL_QME_AME_REPORT",
    }
)
"""The med-legal reports every doctrine discussion can plausibly land in."""

_BRIEFS: frozenset[str] = frozenset({"TRIAL_BRIEF", "DEFENSE_TRIAL_BRIEF"})
"""Trial briefs, applicant and defense."""

_AOE_COE_DEFENSE: frozenset[str] = frozenset(
    {
        "CLAIM_DENIAL_LETTER",
        "COMPENSABILITY_DETERMINATION",
        "ANSWER_TO_APPLICATION",
    }
)
"""Where a threshold compensability defense is first stated in writing."""


DOCTRINE_CONTENT: Mapping[str, DoctrineContent] = {
    "ogilvie": DoctrineContent(
        hook="ogilvie",
        display="Ogilvie — rebuttal of the scheduled rating",
        marker="Ogilvie",
        citation=(
            "Ogilvie v. WCAB (2011) 197 Cal.App.4th 1262, 76 Cal.Comp.Cases 624 "
            "(rebuttal of the scheduled permanent disability rating by vocational "
            "evidence of diminished future earning capacity)."
        ),
        medical_paragraphs=(
            "The scheduled rating produced by the permanent disability rating schedule is a "
            "rebuttable starting point, and this evaluation addresses the Ogilvie question "
            "directly: whether the applicant's diminished future earning capacity departs from "
            "the adjustment the schedule assumes for an impairment of this kind. The vocational "
            "history, the residual functional capacity documented on examination and whatever the "
            "record shows about modified work are the data on which an Ogilvie analysis rests.",
            "For purposes of an Ogilvie rebuttal I have described the applicant's residual "
            "capacity in vocational rather than purely clinical terms: sitting, standing, lifting "
            "and pace tolerances are stated in ranges an evaluator of employability can use. "
            "Whether those tolerances amount to the loss of earning capacity contemplated in "
            "Ogilvie is a question I defer to the vocational expert and to the trier of fact.",
            "I am asked to state whether the industrial injury, rather than a nonindustrial "
            "vocational factor, is what forecloses this applicant's return to the open labor "
            "market. That framing follows Ogilvie, which permits the scheduled rating to be "
            "rebutted only where the diminished future earning capacity is shown to be caused by "
            "the industrial injury itself. My opinion on that causal question is set out above "
            "and is not altered by this addendum.",
        ),
        legal_paragraphs=(
            "The scheduled permanent disability rating is prima facie evidence only. Under "
            "Ogilvie v. WCAB the schedule may be rebutted by evidence that the employee's "
            "diminished future earning capacity differs from that contemplated by the adjustment "
            "factor applied to this impairment, and the rebuttal is evaluated on the record as a "
            "whole rather than on a formulaic recalculation.",
            "An Ogilvie rebuttal requires more than an expert's assertion that the applicant is "
            "unemployable. The proponent must show that the industrial injury is the cause of the "
            "diminished earning capacity and must account for nonindustrial vocational factors; a "
            "vocational opinion that does not perform that separation is not substantial evidence "
            "and cannot carry an Ogilvie rebuttal.",
            "The parties are on notice that the rating issue in this matter will be litigated as "
            "an Ogilvie question. Discovery directed to post-injury earnings, the availability of "
            "modified or alternative work and the vocational expert's methodology is therefore "
            "relevant, and the pretrial conference statement should frame the Ogilvie rebuttal as "
            "a contested issue.",
        ),
        medical_targets=_CORE_MEDLEGAL
        | {
            "VOCATIONAL_EXPERT_REPORT",
            "EARNINGS_CAPACITY_OPINION",
            "TRANSFERABLE_SKILLS_ANALYSIS",
        },
        legal_targets=_BRIEFS
        | {"PD_RATING_CALCULATION_WORKSHEET", "PETITION_RECONSIDERATION_FILED"},
        requires=_RATING_PREREQUISITE,
    ),
    "almaraz_guzman": DoctrineContent(
        hook="almaraz_guzman",
        display="Almaraz/Guzman — alternative impairment rating",
        marker="Guzman",
        citation=(
            "Milpitas Unified School Dist. v. WCAB (Guzman) (2010) 187 Cal.App.4th 808, "
            "75 Cal.Comp.Cases 837 (alternative impairment rating within the four corners "
            "of the AMA Guides)."
        ),
        medical_paragraphs=(
            "Strict application of the AMA Guides does not, in my opinion, produce an accurate "
            "impairment rating for this applicant, and I have therefore provided an alternative "
            "rating under Almaraz/Guzman. As Guzman requires, that alternative remains within the "
            "four corners of the AMA Guides: I have used a different table and a different method "
            "described in the Guides themselves rather than a rating invented outside them.",
            "I state the strict rating first and the Guzman rating second, with the reasoning for "
            "the departure, so that the trier of fact may adopt either. The basis for the Guzman "
            "alternative is the applicant's documented loss of activities of daily living, which "
            "the strict method captures inadequately for the body part at issue here.",
            "A Guzman analysis is only as good as the explanation supporting it. I have "
            "identified the chapter, table and figure of the AMA Guides relied on for the "
            "alternative rating, the reason the strict method understates this impairment, and "
            "the analogy drawn, so that the opinion can be tested as substantial evidence rather "
            "than accepted on the strength of the label.",
        ),
        legal_paragraphs=(
            "Milpitas Unified School Dist. v. WCAB (Guzman) holds that a physician may depart "
            "from strict application of the AMA Guides where strict application does not "
            "accurately reflect the employee's impairment, provided the alternative rating stays "
            "within the four corners of the Guides. A Guzman opinion that reaches outside the "
            "Guides, or that offers no reasoning for the departure, is not substantial evidence.",
            "The burden rests on the party offering the Guzman rating to show both that the "
            "strict rating is inaccurate for this employee and that the alternative selected is "
            "grounded in the Guides. A conclusory statement that the strict rating does not "
            "capture the impairment does not satisfy Guzman and is entitled to no weight.",
            "Because the Guzman issue is dispositive of the permanent disability rating in this "
            "file, the parties should identify, in their pretrial statements, the strict rating, "
            "the Guzman alternative, the provisions of the Guides relied on for each, and the "
            "reasoning that connects them.",
        ),
        medical_targets=_CORE_MEDLEGAL
        | {
            "QME_REPORT_INITIAL",
            "QME_REPORT_SUPPLEMENTAL",
            "MEDICAL_LEGAL_QME_AME_IME",
            "IMPAIRMENT_RATING_WORKSHEET",
        },
        legal_targets=_BRIEFS
        | {"PD_RATING_CALCULATION_WORKSHEET", "PETITION_RECONSIDERATION_FILED"},
        requires=_RATING_PREREQUISITE,
    ),
    "benson": DoctrineContent(
        hook="benson",
        display="Benson — separate awards for separate injuries",
        marker="Benson",
        citation=(
            "Benson v. WCAB (2009) 170 Cal.App.4th 1535, 74 Cal.Comp.Cases 113 "
            "(separate awards for distinct industrial injuries; apportionment between them)."
        ),
        medical_paragraphs=(
            "I am asked to address the Benson question: if a separate industrial injury to this "
            "region is established, whether the permanent disability can be apportioned between "
            "it and the injury evaluated here. I have stated what portion of the current "
            "impairment I could attribute to a separate event on this record, and where the "
            "record does not let me answer, I say so.",
            "A Benson apportionment has to rest on something datable — imaging, a treatment "
            "history, a change in function around a claimed event. I have set out which of those "
            "this file contains and which it does not, so the Benson question can be argued on "
            "the evidence rather than on my willingness to divide a number.",
            "Where the disabilities are inextricably intertwined, Benson permits a combined "
            "award; where they can be parceled out, it does not. My opinion on which of those "
            "this record supports is stated above, with the reasoning, and it is offered on the "
            "assumption that the separate injury is proved rather than as a finding that it was.",
        ),
        legal_paragraphs=(
            "Benson v. WCAB holds that where an employee suffers two or more distinct industrial "
            "injuries, each producing permanent disability, separate awards apportioned between "
            "them are required rather than a single combined award. The exception recognized in "
            "Benson is narrow: a combined award is permissible only where the evaluator cannot "
            "parcel out the causation between the injuries.",
            "Where Benson applies, its consequences are immediate and practical: it affects the "
            "availability of the multiple-disability rating, the permanent disability rate "
            "payable for each injury, and the reach of any prior award. The Benson issue should "
            "therefore be framed separately from general apportionment rather than argued as "
            "part of it.",
            "A medical opinion offered to defeat separate awards under Benson must state, with "
            "reasoning, why the disabilities cannot be parceled out. An evaluator's silence on "
            "the question is not a finding that the injuries are inextricably intertwined, and "
            "Benson is not satisfied by silence.",
        ),
        medical_targets=_CORE_MEDLEGAL | {"APPORTIONMENT_REPORT"},
        legal_targets=_BRIEFS
        | {
            "APPORTIONMENT_WORKSHEET",
            "MOTION_TO_CONSOLIDATE",
            "STIPULATIONS_WITH_REQUEST_FOR_AWARD",
        },
        requires=_BENSON_PREREQUISITE,
    ),
    "escobedo": DoctrineContent(
        hook="escobedo",
        display="Escobedo — substantial evidence for apportionment",
        marker="Escobedo",
        citation=(
            "Escobedo v. Marshalls (2005) 70 Cal.Comp.Cases 604 (en banc) "
            "(apportionment to nonindustrial pathology must rest on substantial "
            "medical evidence)."
        ),
        medical_paragraphs=(
            "Apportionment of permanent disability is a medical question, and Escobedo sets the "
            "standard this opinion must meet: I must state what approximate percentage of the "
            "permanent disability is caused by the industrial injury and what percentage is "
            "caused by other factors, and I must explain how and why I reached those percentages.",
            "Escobedo requires more than the recitation of a preexisting condition: any "
            "nonindustrial pathology I apportion to must be shown to be causing permanent "
            "disability now, not merely to be visible or to predate the injury. Where I have "
            "apportioned, the findings supporting that conclusion are set out above; where the "
            "record shows only the presence of a condition, I have not apportioned to it.",
            "Where I cannot apportion to a reasonable medical probability, Escobedo requires that "
            "I say so rather than supply a number. This addendum distinguishes the portion of the "
            "disability I can allocate with the necessary certainty from the portion I cannot.",
        ),
        legal_paragraphs=(
            "Escobedo v. Marshalls, decided en banc, requires that a medical opinion on "
            "apportionment explain the how and why of the apportionment determination, and that "
            "the physician find the nonindustrial factor to be causing permanent disability "
            "rather than merely to be present. An opinion that recites a preexisting condition "
            "without that analysis is not substantial evidence under Escobedo.",
            "The burden of proving apportionment rests on the defendant, and Escobedo makes "
            "clear that the burden is not carried by a percentage stated without reasoning. Any "
            "apportionment adopted in this matter must be traceable to the record evidence the "
            "evaluator identified.",
            "The parties should be prepared to address whether the apportionment opinion in this "
            "file satisfies Escobedo, and if it does not, whether the remedy is a supplemental "
            "report, the deposition of the evaluator, or an award unapportioned as to the "
            "deficient component.",
        ),
        medical_targets=_CORE_MEDLEGAL
        | {"APPORTIONMENT_REPORT", "QME_REPORT_SUPPLEMENTAL"},
        legal_targets=_BRIEFS
        | {"APPORTIONMENT_WORKSHEET", "PETITION_RECONSIDERATION_FILED"},
        requires=_RATING_PREREQUISITE,
    ),
    "kite": DoctrineContent(
        hook="kite",
        display="Kite — adding rather than combining impairments",
        marker="Kite",
        citation=(
            "Athens Administrators v. WCAB (Kite) (2013) 78 Cal.Comp.Cases 213 (writ den.) "
            "(impairments added rather than combined where a synergistic effect is shown)."
        ),
        medical_paragraphs=(
            "The Combined Values Chart assumes that impairments affect independent functions. "
            "Where two impairments act on the same activities of daily living the chart "
            "understates the resulting disability, and Kite permits the impairments to be added "
            "instead. I have addressed that question expressly rather than defaulting to the "
            "chart.",
            "An opinion that impairments should be added under Kite has to identify the shared "
            "activities the impairments both degrade, and say how the second compounds the first "
            "rather than merely accompanying it. Addition under Kite is not automatic, and I do "
            "not apply it merely because more than one body part is involved.",
            "Where the synergy Kite describes is absent I say so and use the Combined Values "
            "Chart. In this file I have stated which impairments I would add and which I would "
            "combine, with the functional reasoning for each, so that the rating can be "
            "constructed either way.",
        ),
        legal_paragraphs=(
            "Athens Administrators v. WCAB (Kite) recognizes that impairments may be added rather "
            "than combined where the medical evidence establishes a synergistic effect on the "
            "same activities of daily living. Kite is a writ denied case and is persuasive rather "
            "than binding, but the analysis it approves is now routinely applied at the trial "
            "level.",
            "A Kite rating requires medical evidence of the synergy, not an arithmetic "
            "preference. The proponent must point to a reasoned explanation of how the "
            "impairments interact; without it the Combined Values Chart applies and a Kite "
            "addition should be rejected.",
            "The difference between a Kite addition and a combined rating is material to the "
            "permanent disability award in this matter and therefore to the value of the case. "
            "The parties should frame the Kite question as a contested rating issue and identify "
            "the medical evidence supporting their positions.",
        ),
        medical_targets=_CORE_MEDLEGAL | {"IMPAIRMENT_RATING_WORKSHEET"},
        legal_targets=_BRIEFS
        | {"PD_RATING_CALCULATION_WORKSHEET", "PD_RATING_CONVERSION"},
        requires=_KITE_PREREQUISITE,
    ),
    "going_and_coming": DoctrineContent(
        hook="going_and_coming",
        display="Going and coming rule",
        marker="going and coming",
        citation=(
            "Hinojosa v. WCAB (1972) 8 Cal.3d 150, 37 Cal.Comp.Cases 724 "
            "(going and coming rule; special-mission and required-vehicle exceptions)."
        ),
        medical_paragraphs=(
            "I am asked to describe the circumstances of the injury as the applicant reported "
            "them, including where the applicant was travelling, in what vehicle, at whose "
            "direction and for what purpose. Those facts bear on the going and coming rule, which "
            "is a legal question I do not decide; I report the history and state whether the "
            "mechanism described is consistent with the injuries found on examination.",
            "Whether the going and coming rule bars this claim is outside my role as a medical "
            "evaluator. My opinion is confined to industrial causation in the medical sense — "
            "whether the mechanism described could produce the pathology documented — and it "
            "stands or falls independently of where the trip is ultimately held to have begun.",
            "For completeness I note the facts a going and coming analysis would turn on, as the "
            "applicant related them at the time of the evaluation: the origin and destination of "
            "the trip, whether a work vehicle or a personal vehicle was used, and whether the "
            "applicant was carrying tools or performing an errand for the employer.",
        ),
        legal_paragraphs=(
            "The going and coming rule bars compensation for injuries sustained during an "
            "ordinary local commute, on the reasoning that the employment relationship is "
            "suspended from the time the employee leaves work until the employee returns. The "
            "rule and its limits are described in Hinojosa v. WCAB, which cautions that it is "
            "riddled with exceptions and is not to be applied mechanically.",
            "Two exceptions to the going and coming rule are the ones most often litigated. The "
            "special mission exception applies where the employee is engaged in an extraordinary "
            "errand at the employer's request; the required vehicle exception applies where the "
            "employer expressly or impliedly requires the employee to furnish a vehicle for "
            "work. Whether either is available here depends on facts still to be established.",
            "The party asserting an exception to the going and coming rule bears the burden of "
            "establishing the facts that trigger it. Discovery should therefore be directed to "
            "the purpose of the trip, the employer's expectations regarding use of a personal "
            "vehicle, and any mileage or vehicle allowance paid.",
        ),
        medical_targets=frozenset({"QME_COMPREHENSIVE_REPORT", "AME_COMPREHENSIVE_REPORT"}),
        legal_targets=_AOE_COE_DEFENSE | _BRIEFS | {"INVESTIGATION_REPORT"},
        requires=_CONTESTED_PREREQUISITE,
    ),
    "sibtf": DoctrineContent(
        hook="sibtf",
        display="SIBTF — Subsequent Injuries Benefits Trust Fund",
        marker="4751",
        citation=(
            "Labor Code section 4751 (Subsequent Injuries Benefits Trust Fund; preexisting "
            "labor-disabling permanent partial disability combined with a subsequent "
            "industrial injury)."
        ),
        medical_paragraphs=(
            "This addendum addresses what Labor Code section 4751 asks of a medical evaluator: "
            "whether a preexisting condition, if established, was labor disabling before the "
            "industrial injury, and what the combined effect of it and the current impairment "
            "would be. I have answered on the records provided and identified what a section "
            "4751 claim would still need.",
            "Section 4751 requires that the preexisting disability be labor disabling rather than "
            "merely present, and that the subsequent industrial injury combine with it to produce "
            "a substantially greater disability. Where the records establish a prior condition I "
            "have stated it as a whole person figure with the basis for it, so the section 4751 "
            "threshold can be tested against evidence rather than asserted.",
            "Where a prior labor-disabling condition is established, my opinion on whether its "
            "combined effect with the current industrial injury exceeds the sum of their separate "
            "effects is stated above with the reasoning. Whether that satisfies the thresholds of "
            "section 4751 is a legal determination that I do not make.",
        ),
        legal_paragraphs=(
            "Labor Code section 4751 provides benefits from the Subsequent Injuries Benefits "
            "Trust Fund where an employee with a preexisting permanent partial disability "
            "sustains a subsequent industrial injury and the combined permanent disability "
            "reaches seventy percent or more. The section 4751 thresholds must be pleaded and "
            "proved.",
            "A claim under section 4751 requires either a preexisting disability of at least "
            "thirty-five percent, or a subsequent injury to an opposite and corresponding member "
            "producing at least five percent, together with the statutory combined threshold. The "
            "Fund is a separate party and must be joined; a case in chief resolved without "
            "joinder does not resolve the claim against it.",
            "The applicant is on notice that the section 4751 claim will require evidence of the "
            "labor-disabling character of the preexisting condition at the time of the subsequent "
            "injury, independent of the medical evidence supporting the case in chief.",
        ),
        medical_targets=frozenset(
            {
                "QME_COMPREHENSIVE_REPORT",
                "AME_COMPREHENSIVE_REPORT",
                "IMPAIRMENT_RATING_WORKSHEET",
            }
        ),
        legal_targets=frozenset(
            {
                "MOTION_FOR_JOINDER",
                "TRIAL_BRIEF",
                "CASE_ANALYSIS_MEMO",
                "SETTLEMENT_VALUATION_MEMO",
            }
        ),
        requires=_RATING_PREREQUISITE,
    ),
    "death_dependency": DoctrineContent(
        hook="death_dependency",
        display="Death benefits and dependency",
        marker="3501",
        citation=(
            "Labor Code sections 3501, 3502 and 3503, and section 4702 (death benefits; "
            "conclusive presumptions of total dependency, dependency in fact, and "
            "allocation among dependents)."
        ),
        medical_paragraphs=(
            "This addendum addresses the medical question underlying the dependency claim: "
            "whether the industrial injury or exposure was a contributing cause of death. The "
            "dependency determinations governed by Labor Code section 3501 and the provisions "
            "following it are legal rather than medical, and I express no opinion on them.",
            "I have reviewed the terminal records, the certificate of death and the treatment "
            "history for the purpose of determining industrial causation. Which persons are "
            "dependents within the meaning of section 3501, and which must prove dependency in "
            "fact, will be determined on family circumstances that fall outside a medical "
            "evaluation.",
            "In my opinion the industrial condition was a contributing cause of death to a "
            "reasonable medical probability. Allocation of the death benefit among the dependents "
            "identified under section 3501 and the sections following it is a matter for the "
            "trier of fact.",
        ),
        legal_paragraphs=(
            "Labor Code section 3501 conclusively presumes total dependency for a surviving "
            "spouse who earned no income in the twelve months preceding the injury, and for "
            "children under the age of eighteen or incapacitated from earning. The presumption is "
            "conclusive: evidence of actual contribution is neither required to establish it nor "
            "admissible to defeat it.",
            "Persons outside the conclusive presumption of section 3501 may still establish total "
            "or partial dependency in fact, determined as of the date of injury, and the death "
            "benefit is then allocated among total and partial dependents under Labor Code "
            "section 4702. The distinction drives the amount payable and should be resolved "
            "before any settlement is submitted for approval.",
            "The parties should identify every claimed dependent, the basis of dependency "
            "asserted under section 3501 or in fact, and whether a guardian ad litem is required "
            "for any minor claimant, so that the death benefit can be allocated in a single "
            "proceeding.",
        ),
        medical_targets=frozenset({"QME_COMPREHENSIVE_REPORT", "AME_COMPREHENSIVE_REPORT"}),
        legal_targets=frozenset(
            {
                "APPLICATION_FOR_ADJUDICATION_DEATH",
                "STIPULATIONS_DEATH_CASE",
                "COMPROMISE_AND_RELEASE_DEPENDENCY",
                "PETITION_GUARDIAN_AD_LITEM",
                "TRIAL_BRIEF",
            }
        ),
        requires=_DEATH_PREREQUISITE,
    ),
    "lc3208_3_psych": DoctrineContent(
        hook="lc3208_3_psych",
        display="Labor Code 3208.3 — psychiatric injury threshold",
        marker="3208.3",
        citation=(
            "Labor Code section 3208.3 (psychiatric injury; six-month employment bar, "
            "predominant-cause standard, and the sudden and extraordinary employment "
            "condition exception)."
        ),
        medical_paragraphs=(
            "This psychiatric evaluation is framed by Labor Code section 3208.3, which requires "
            "that actual events of employment be the predominant cause of the psychiatric injury "
            "when all causes are considered together. I have therefore weighed the industrial and "
            "the nonindustrial stressors against each other rather than listing them.",
            "The diagnosis is stated in the terminology of the diagnostic manual, as section "
            "3208.3 requires, and the industrial and nonindustrial causes are assigned "
            "approximate percentages with the reasoning for each. Section 3208.3 makes causation "
            "a threshold question rather than an apportionment question, and this opinion "
            "addresses it in those terms.",
            "Section 3208.3 also carries an employment-duration bar, which is a question of "
            "personnel records rather than of psychiatry; I note it because it is dispositive if "
            "it applies, and because the sudden and extraordinary employment condition exception "
            "to it turns on the same events of employment I have weighed above.",
        ),
        legal_paragraphs=(
            "Labor Code section 3208.3 imposes a heightened threshold for psychiatric injury: the "
            "employee must prove by a preponderance of the evidence that actual events of "
            "employment were predominant as to all causes combined. The section 3208.3 threshold "
            "is an element of the claim rather than an affirmative defense, and the burden is the "
            "applicant's.",
            "Section 3208.3, subdivision (d), bars compensation for a psychiatric injury unless "
            "the employee has been employed for at least six months, which need not be "
            "continuous, except where the injury is caused by a sudden and extraordinary "
            "employment condition. That exception is construed narrowly and is not satisfied by "
            "an ordinary, if serious, workplace event.",
            "The parties should expect the section 3208.3 threshold to be litigated as a separate "
            "issue, on medical evidence that assigns percentages to the industrial and the "
            "nonindustrial causes. An evaluation that lists stressors without weighing them does "
            "not permit a finding under section 3208.3.",
        ),
        medical_targets=frozenset(
            {
                "PSYCH_EVAL_REPORT_QME_AME",
                "PSYCHOLOGICAL_TESTING_PROTOCOL",
                "QME_COMPREHENSIVE_REPORT",
                "AME_COMPREHENSIVE_REPORT",
            }
        ),
        legal_targets=_BRIEFS | {"CLAIM_DENIAL_LETTER", "ANSWER_TO_APPLICATION"},
        requires=_PSYCH_CLAIM_PREREQUISITE,
    ),
    "gfpa": DoctrineContent(
        hook="gfpa",
        display="Good faith personnel action defense",
        marker="personnel action",
        citation=(
            "Labor Code section 3208.3, subdivision (h) (a psychiatric injury substantially "
            "caused by a lawful, nondiscriminatory, good faith personnel action is not "
            "compensable)."
        ),
        medical_paragraphs=(
            "Labor Code section 3208.3, subdivision (h), makes a psychiatric injury "
            "noncompensable where it is substantially caused by a lawful, nondiscriminatory, good "
            "faith personnel action. Where the employment events described include conduct of "
            "that character, I have separated the reaction to it from the reaction to other "
            "events of employment and stated approximate percentages for each.",
            "Whether the employment events the applicant describes were a lawful, "
            "nondiscriminatory and good faith personnel action is a question outside my role. "
            "What I can supply is the causation arithmetic the defense turns on: the percentage "
            "attributable to events of that character, stated separately, so the trier of fact "
            "can apply the defense to the medical opinion rather than infer it.",
            "To the extent the employment events described qualify as personnel action, my "
            "opinion assigns them the percentage of causation stated above, with the remainder "
            "attributable to the other events described. I express no view on whether the "
            "employer's conduct was lawful or carried out in good faith.",
        ),
        legal_paragraphs=(
            "Labor Code section 3208.3, subdivision (h), bars a psychiatric injury claim where "
            "the injury was substantially caused by a lawful, nondiscriminatory, good faith "
            "personnel action. The defense requires the employer to establish that the conduct "
            "was a personnel action, that it was lawful and nondiscriminatory, and that it was "
            "carried out in good faith.",
            "The good faith personnel action defense turns on a percentage: the personnel action "
            "must be a substantial cause of the psychiatric injury, which is at least "
            "thirty-five to forty percent of the causation from all sources combined. Medical "
            "evidence that does not quantify that contribution cannot establish the defense.",
            "Conduct of the kind ordinarily asserted under this defence — criticism of "
            "performance, a change in assignment, the initiation of a disciplinary process — is "
            "personnel action within the meaning of the statute; that much is rarely the "
            "battleground. What is disputed is lawfulness and good faith, and the parties should "
            "come prepared to try both.",
        ),
        medical_targets=frozenset(
            {
                "PSYCH_EVAL_REPORT_QME_AME",
                "QME_COMPREHENSIVE_REPORT",
                "AME_COMPREHENSIVE_REPORT",
            }
        ),
        legal_targets=_BRIEFS
        | {"CLAIM_DENIAL_LETTER", "ANSWER_TO_APPLICATION", "DEFENSE_CASE_ANALYSIS"},
        requires=_GFPA_PREREQUISITE,
    ),
    "firefighter_presumption": DoctrineContent(
        hook="firefighter_presumption",
        display="Firefighter cancer presumption",
        marker="3212.1",
        citation=(
            "Labor Code section 3212.1 (rebuttable cancer presumption for firefighters and "
            "peace officers demonstrating exposure to a known carcinogen)."
        ),
        medical_paragraphs=(
            "This evaluation addresses the medical questions the cancer presumption in Labor Code "
            "section 3212.1 would raise: any diagnosis relied on and its date, the period of "
            "active service, and whether the record shows exposure to a known carcinogen during "
            "that service. The presumption itself is applied by the trier of fact and not by the "
            "evaluator.",
            "Section 3212.1 permits rebuttal only by evidence that the carcinogen to which the "
            "member was exposed is not reasonably linked to the disabling cancer. I have "
            "identified the exposures documented in the record and the literature bearing on that "
            "link, without expressing an opinion on whether a rebuttal succeeds.",
            "Service history and the timing of any diagnosis are set out above because together "
            "they determine whether the extended post-service period described in section 3212.1 "
            "is available. My causation opinion is stated independently of the presumption so "
            "that it remains useful if the presumption does not apply.",
        ),
        legal_paragraphs=(
            "Labor Code section 3212.1 establishes a rebuttable presumption that cancer "
            "developing in a qualifying firefighter or peace officer arose out of and in the "
            "course of employment, where the member demonstrates exposure to a known carcinogen "
            "during the period of service. The presumption extends beyond the term of service by "
            "three months for each year served, to a maximum of 120 months.",
            "The employer may rebut the section 3212.1 presumption only with evidence that the "
            "primary site carcinogen to which the member was exposed is not reasonably linked to "
            "the disabling cancer. A general denial of causation, or an expert opinion that does "
            "not address the specific carcinogen and the specific cancer, does not meet the "
            "statutory standard.",
            "The threshold facts under section 3212.1 — qualifying employment, demonstrated "
            "exposure to a known carcinogen, and the timing of the diagnosis — are to be pleaded "
            "and proved by the applicant, and the parties should address them separately from the "
            "general causation dispute.",
        ),
        medical_targets=frozenset(
            {
                "QME_COMPREHENSIVE_REPORT",
                "AME_COMPREHENSIVE_REPORT",
                "MEDICAL_LEGAL_QME_AME_IME",
            }
        ),
        legal_targets=_AOE_COE_DEFENSE | _BRIEFS,
        requires=_SAFETY_MEMBER_PREREQUISITE,
    ),
    "imr_constitutionality": DoctrineContent(
        hook="imr_constitutionality",
        display="IMR due-process challenge",
        marker="Stevens",
        citation=(
            "Stevens v. WCAB (2015) 241 Cal.App.4th 1074 and Ramirez v. WCAB (2017) "
            "10 Cal.App.5th 205 (due-process challenges to independent medical review; "
            "Labor Code section 4610.6, subdivision (h), appeal grounds)."
        ),
        medical_paragraphs=(
            "The treatment at issue went to utilization review and from there to independent "
            "medical review. Stevens v. WCAB confirms that medical necessity is determined in "
            "that forum rather than by an evaluator, whatever the determination held, so my "
            "opinion on the reasonableness of the requested treatment is offered as medical "
            "evidence and not as a review of it.",
            "Stevens holds that the reviewer's anonymity is permissible, while recognizing that a "
            "determination founded on a plainly erroneous factual premise may be challenged. I "
            "have therefore checked the determination against the records supplied to me and "
            "identified any factual premise in it that those records do not support.",
            "Where a determination rests on an incomplete record the appropriate medical step is "
            "a renewed request supported by the omitted documentation. Stevens and the decisions "
            "following it leave the substantive question of medical necessity with the review "
            "process, so this addendum documents the deficiency rather than substituting my "
            "judgment for the reviewer's.",
        ),
        legal_paragraphs=(
            "Stevens v. WCAB rejected a facial due-process challenge to independent medical "
            "review, holding that the Legislature may assign medical necessity determinations to "
            "a non-judicial reviewer, while recognizing that a determination may be set aside on "
            "the statutory grounds preserved in Labor Code section 4610.6, subdivision (h).",
            "Ramirez v. WCAB followed Stevens in rejecting constitutional challenges to "
            "independent medical review while confirming that the statutory appeal grounds are "
            "real: fraud, conflict of interest, bias, a plainly erroneous material finding of "
            "fact, and an act in excess of powers. An appeal that fits none of those grounds "
            "fails however wrong the determination appears.",
            "The remedy where such an appeal succeeds is a further review by a different "
            "reviewer, not an award of the requested treatment. The parties should frame this "
            "dispute in the terms Stevens and Ramirez leave open rather than as a merits review "
            "of medical necessity.",
        ),
        medical_targets=_CORE_MEDLEGAL,
        legal_targets=frozenset(
            {
                "INDEPENDENT_MEDICAL_REVIEW_DECISION",
                "IMR_DETERMINATION_FORM",
                "UR_APPEAL_LETTER",
                "PETITION_RECONSIDERATION_FILED",
                "TRIAL_BRIEF",
            }
        ),
        requires=_IMR_PREREQUISITE,
    ),
    "ab5_dynamex": DoctrineContent(
        hook="ab5_dynamex",
        display="AB 5 / Dynamex — employee status",
        marker="Dynamex",
        citation=(
            "Dynamex Operations West, Inc. v. Superior Court (2018) 4 Cal.5th 903, and "
            "Labor Code section 2775 (ABC test for employee status)."
        ),
        medical_paragraphs=(
            "Where employment status is contested under the standard described in Dynamex "
            "Operations West, Inc. v. Superior Court, that contest does not affect my medical "
            "opinions, which address the injury, its cause in the medical sense and the "
            "resulting impairment. I record the working relationship only as the applicant "
            "described it.",
            "Whether the working relationship described to me satisfies the test approved in "
            "Dynamex is a legal question on which I express no opinion. My causation opinion "
            "assumes only that the work activity described occurred, and it does not depend on "
            "how that relationship is ultimately characterized.",
            "I have documented the applicant's account of who supplied the tools, who set the "
            "hours and how the work was assigned, because those facts are relevant to the Dynamex "
            "analysis even though the conclusion belongs to the trier of fact.",
        ),
        legal_paragraphs=(
            "Dynamex Operations West, Inc. v. Superior Court adopted the ABC test for determining "
            "whether a worker is an employee, since codified at Labor Code section 2775: the "
            "hiring entity bears the burden of establishing that the worker is free from its "
            "control, performs work outside the usual course of its business, and is customarily "
            "engaged in an independently established trade of the same nature.",
            "Each prong of the Dynamex test must be satisfied, and the failure of any one prong "
            "establishes employee status. Because the burden rests on the hiring entity, an "
            "incomplete record on any prong resolves against the party asserting independent "
            "contractor status.",
            "The statutory exemptions return the analysis to the multifactor common law standard "
            "rather than establishing independent contractor status outright. The parties should "
            "identify which test they contend applies and, where an exemption is claimed, the "
            "specific statutory basis for it, before the Dynamex issue is submitted.",
        ),
        medical_targets=frozenset({"QME_COMPREHENSIVE_REPORT", "AME_COMPREHENSIVE_REPORT"}),
        legal_targets=_AOE_COE_DEFENSE | _BRIEFS | {"INVESTIGATION_REPORT"},
        requires=_CONTESTED_PREREQUISITE,
    ),
    "lc4664_prior_award": DoctrineContent(
        hook="lc4664_prior_award",
        display="Labor Code 4664 — apportionment to a prior award",
        marker="4664",
        citation=(
            "Labor Code section 4664, subdivision (b) (conclusive presumption that a prior "
            "award of permanent disability still exists), and subdivision (c) (lifetime "
            "accumulation cap by region of the body)."
        ),
        medical_paragraphs=(
            "Where a prior award of permanent disability affecting the same region is "
            "established, Labor Code section 4664, subdivision (b), conclusively presumes that "
            "the prior disability existed at the time of the subsequent injury. This opinion "
            "therefore addresses the current impairment and the extent to which it would overlap "
            "a previously awarded disability, without assuming that such an award has been "
            "proved.",
            "Apportionment under section 4664 differs from apportionment to nonindustrial "
            "causation: it operates on the prior award rather than on medical causation, and it "
            "requires that the prior and the current disability overlap in the same region. "
            "Where a prior award is produced, I have described in functional terms what would "
            "overlap the impairment found here, so that the calculation can be performed.",
            "I have stated the current whole person impairment before any deduction. The "
            "subtraction of the previously awarded disability required by section 4664 is a "
            "rating and legal exercise rather than a medical one, and I have not performed it in "
            "this report.",
        ),
        legal_paragraphs=(
            "Labor Code section 4664, subdivision (b), provides that where a prior award of "
            "permanent disability has issued, that disability is conclusively presumed to still "
            "exist at the time of any subsequent injury. The presumption relieves the defendant "
            "of proving that the prior disability continues; it does not relieve the defendant of "
            "proving overlap.",
            "A defendant asserting section 4664 must produce the prior award and must establish "
            "that the prior and the current permanent disability overlap. Absent proof of "
            "overlap the conclusive presumption reduces nothing, and the burden on both elements "
            "rests with the defendant.",
            "Section 4664 also caps the accumulation of permanent disability awards for the same "
            "region of the body at one hundred percent over the employee's lifetime. The parties "
            "should identify every prior award affecting the regions at issue so that the section "
            "4664 analysis can be completed on a full record.",
        ),
        medical_targets=_CORE_MEDLEGAL | {"APPORTIONMENT_REPORT"},
        legal_targets=_BRIEFS
        | {
            "APPORTIONMENT_WORKSHEET",
            "ANSWER_TO_APPLICATION",
            "PD_RATING_CALCULATION_WORKSHEET",
        },
        requires=_RATING_PREREQUISITE,
    ),
}
"""Every doctrine hook's renderable content, keyed by hook name."""


def content_flags_for(doctrine_hooks: Sequence[str], subtype: str) -> tuple[str, ...]:
    """The hooks in *doctrine_hooks* that carry content for *subtype*.

    Sorted and deduplicated, so the flag tuple on a planned document is a
    function of the set of hooks rather than of the order a seed listed them —
    two seeds naming the same hooks produce the same document.

    Args:
        doctrine_hooks: the seed's ``lifecycle.doctrine_hooks``.
        subtype: canonical classifier subtype key.

    Returns:
        Sorted, deduplicated hook names. Empty when no hook targets *subtype*.
    """
    return tuple(
        sorted(
            {
                hook
                for hook in doctrine_hooks
                if (content := DOCTRINE_CONTENT.get(hook)) is not None
                and content.targets_subtype(subtype)
            }
        )
    )


def hook_is_supported(hook: str, subject: Any) -> bool:
    """``True`` when *subject* can support *hook*'s argument.

    Args:
        hook: a ``DoctrineHook`` value.
        subject: a :class:`~wc_caseload_engine.seeds.CaseSeed` or a
            :class:`DoctrineFacts`.

    An unknown hook answers ``False`` — it has no content, so nothing it could
    support exists. A hook with no prerequisite answers ``True``.
    """
    content = DOCTRINE_CONTENT.get(hook)
    if content is None:
        return False
    if content.requires is None:
        return True
    return content.requires.satisfied_by(subject)


def supported_hooks(hooks: Sequence[str], subject: Any) -> tuple[str, ...]:
    """The subset of *hooks* that fits *subject*, order preserved.

    This is the filter ``auto:`` derivation draws through: a hook nobody asked
    for by name has no claim to be in a case it does not fit.
    """
    facts = _as_facts(subject)
    return tuple(hook for hook in hooks if hook_is_supported(hook, facts))


def unsupported_hook_warnings(hooks: Sequence[str], subject: Any) -> tuple[str, ...]:
    """One warning per explicitly seeded hook whose prerequisite fails.

    The hook is *kept* — ISC-29's rule is that an explicit control wins, and it
    wins loudly. What the case gets is a warning naming the doctrine, what the
    seed would have to say for it to fit, and the fact that the document will
    argue it anyway.
    """
    facts = _as_facts(subject)
    warnings: list[str] = []
    for hook in hooks:
        content = DOCTRINE_CONTENT.get(hook)
        if content is None or content.requires is None:
            continue
        if content.requires.satisfied_by(facts):
            continue
        warnings.append(
            f"lifecycle.doctrine_hooks names {hook} on a case that cannot support it: "
            f"{content.requires.description}. The hook is kept and its language will be "
            "rendered (an explicit seed wins), but the argument will not match the rest "
            "of the file."
        )
        log.warning(
            "doctrine.unsupported_hook",
            hook=hook,
            requirement=content.requires.description,
        )
    return tuple(warnings)


def register_for_subtype(subtype: str) -> str:
    """The register *subtype* is written in — medical addendum or authorities.

    A subtype carries one register across every hook (asserted by
    ``tests/test_doctrine_content.py``), so this can answer from the first hook
    that claims it. A subtype no hook targets answers :data:`LEGAL_REGISTER`,
    which is the conservative default: it is never reached through
    :func:`content_flags_for`, and a caller that reaches it anyway gets a
    heading rather than an exception.
    """
    for content in DOCTRINE_CONTENT.values():
        register = content.register_for(subtype)
        if register is not None:
            return register
    return LEGAL_REGISTER


def heading_for_register(register: str) -> str:
    """The section heading for *register*."""
    return MEDICAL_HEADING if register == MEDICAL_REGISTER else LEGAL_HEADING


def doctrine_markers() -> tuple[str, ...]:
    """Every hook's marker, sorted — the grep surface of this module."""
    return tuple(sorted(content.marker for content in DOCTRINE_CONTENT.values()))


__all__ = [
    "DOCTRINE_CONTENT",
    "LEGAL_HEADING",
    "LEGAL_REGISTER",
    "MEDICAL_HEADING",
    "MEDICAL_REGISTER",
    "DoctrineContent",
    "DoctrineFacts",
    "DoctrinePrerequisite",
    "content_flags_for",
    "doctrine_markers",
    "heading_for_register",
    "hook_is_supported",
    "register_for_subtype",
    "supported_hooks",
    "unsupported_hook_warnings",
]
