"""Cited epidemiology for the medical-history layer — the answer key, not the answer.

This module is note C (``Plans/research/wcce-medical-story/clinical-grounding-tables.md``)
turned into data. It holds no logic about *this* engine: it is a table of what the
literature says about real people, so that a synthetic applicant's pre-existing
conditions can be drawn at rates a defence QME would recognise instead of invented
on the spot.

The point of separating it from the sampler is calibration. `medical_history.py`
tunes archetype bundles until the corpus reproduces the numbers *here*, and the
property test asserts that it did. If the two lived in one module the target and
the thing being measured would be the same edit, and "the marginals match" would
stop being a claim about anything.

Three disciplines are inherited from the research notes and are load-bearing.

**A NOT-FOUND cell is omitted, never stored as ``None`` or ``0.0``.** Note C's own
rule, and it survives translation for the reason it was written: silently reading
"we did not find a figure" as "the rate is zero" would misrepresent the research as
more complete than it is, and a zero is indistinguishable from a measurement once it
is in a table. :func:`age_band_rate` returns ``None`` on a miss, and every gap this
module knows it has is named in :data:`KNOWN_COVERAGE_GAPS` so the holes can be
counted rather than discovered.

**Age bands are stored as each source reported them.** Five incompatible shapes
appear below — decades (Brinjikji), cutoffs (Culvenor), compound ranges (Sher),
ten-year-ish bands (Jarraya) and open tails (CDC). Normalising them into one scheme
during transcription would manufacture precision no study measured.

**Every value carries its own provenance, inline.** :class:`Citation` pairs a number
with its source and a confidence tag; :class:`Knob` pairs a design choice with the
tag note F assigns it — ``measured``, ``counsel_confirmed``, ``counsel_unconfirmed``
or ``invented`` — and, for anything short of measured, the interview question that
would upgrade it. This is the ``money.UNCONFIRMED_RATE_TABLE`` pattern: the caveat
travels with the value so a reader who copies the number cannot lose it on the way.

**What is deliberately absent.** Note C §2.3 and §2.8 carry two rows —
ankle osteoarthritis and prior injury/surgery at the same site — whose
``apportionment_basis`` is ``case_specific_history`` rather than
``population_epidemiology``. They are not in :data:`CONDITION_CATALOG`, and that is
the finding rather than an omission: 75-80% of ankle OA is post-traumatic, so
neither row can be drawn from an age-keyed probability table at all. They need a
qualifying prior event on the seed, which is what
:class:`~wc_caseload_engine.medical_history.PriorClaim` exists to carry.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

type Sex = Literal["female", "male"]
"""The two values every sex-conditioned table below reports.

Not a statement about people. It is the split SEER, NHANES and the Framingham
cohorts published, and a table cannot be keyed on a distinction its source did not
measure.
"""

SEXES: tuple[str, ...] = ("female", "male")

type BmiBand = Literal["normal_or_under", "overweight", "obese", "severely_obese"]
"""Four bands, because four is what the cited sources can tell apart.

``obese`` is BMI 30-39.9 and ``severely_obese`` is 40+, which is the line the
arthroplasty literature actually turns on (note C §4.1: the periprosthetic-infection
odds ratio is flat at 35-39.9 and triples at 40). Splitting ``normal_or_under`` from
``overweight`` finer than this would outrun the data.
"""

BMI_BANDS: tuple[str, ...] = ("normal_or_under", "overweight", "obese", "severely_obese")

OBESE_BANDS: frozenset[str] = frozenset({"obese", "severely_obese"})
"""The bands CDC's obesity prevalence figure counts (BMI >= 30)."""

type SmokingStatus = Literal["never", "former", "current"]

SMOKING_STATUSES: tuple[str, ...] = ("never", "former", "current")

type Confidence = Literal["strong", "single_study", "approximate"]
"""Note C's evidence grade for one published number.

``strong`` is a systematic review, meta-analysis or large registry;
``single_study`` is one well-cited primary study not independently replicated;
``approximate`` is standard clinical teaching, a triangulated figure, or a range
reported without a point estimate.
"""

type Tag = Literal[
    "measured",
    "interpolated",
    "extrapolated",
    "counsel_confirmed",
    "counsel_unconfirmed",
    "invented",
]
"""Note F's provenance grade for one *design choice*.

Distinct from :data:`Confidence`, which grades a published number. A knob built by
combining two measured inputs is a derivation and is never tagged ``measured``, no
matter how good its inputs are — note F states that rule and this module keeps it.

``interpolated`` and ``extrapolated`` exist because "measured" was being asked to
cover values nobody measured. A gradient tagged ``measured`` as a whole was carrying
a severe-obesity band read off a rising curve past its last published point; that is
a reading of a measurement, not a measurement, and review was right that it needed
its own grade. ``interpolated`` sits *inside* the published range, ``extrapolated``
outside it — the second is the weaker claim and the one worth spotting.
"""

type ApportionmentBasis = Literal["population_epidemiology", "case_specific_history"]
"""Whether a contributor can be drawn from an age table, or needs a seeded event.

A real fork in generation logic rather than a label. Every entry in
:data:`CONDITION_CATALOG` is ``population_epidemiology``; see the module docstring
for the two note C rows that are not, and why they are absent.
"""

type BodySystem = Literal[
    "musculoskeletal",
    "endocrine",
    "cardiovascular",
    "psychiatric",
    "neurologic",
    "oncologic",
]


@dataclass(frozen=True, slots=True)
class Citation:
    """One published number, with the source and grade it was published under."""

    value: float
    source: str
    confidence: Confidence


@dataclass(frozen=True, slots=True)
class Knob:
    """One design choice this engine had to make, stating what it rests on.

    ``source`` is a citation when ``tag`` is ``measured``; for everything else it is
    the interview question that would upgrade the tag. Both are the same field on
    purpose — a knob is never allowed to carry neither.
    """

    value: float
    tag: Tag
    rationale: str
    source: str

    def __post_init__(self) -> None:
        if not self.rationale.strip() or not self.source.strip():
            raise ValueError(
                f"knob {self.value!r} has an empty rationale or source — a value with "
                "no provenance is the thing this type exists to make impossible"
            )


# ---------------------------------------------------------------------------
# Age-band resolution
# ---------------------------------------------------------------------------

_DECADE = re.compile(r"^(\d+)s$")
_RANGE = re.compile(r"^(\d+)-(\d+)$")
_TAIL = re.compile(r"^(\d+)\+$")
_UNDER = re.compile(r"^<(\d+)$")
_ALL_AGES = "all_ages"


def band_contains(band: str, age: int) -> bool:
    """Whether *band*, written the way its source wrote it, covers *age*.

    Five shapes, because five is what the literature uses: ``"20s"`` (decade),
    ``"50-59"`` (closed range, inclusive both ends), ``"60+"`` (open tail),
    ``"<40"`` (open head) and ``"all_ages"``.

    Raises:
        ValueError: on a band this function does not recognise. A silent ``False``
            would read as "no source covers this age" and send the caller down the
            NOT-FOUND path, turning a typo into a fabricated coverage gap.
    """
    if band == _ALL_AGES:
        return True
    if match := _DECADE.match(band):
        decade = int(match.group(1))
        return decade <= age < decade + 10
    if match := _RANGE.match(band):
        return int(match.group(1)) <= age <= int(match.group(2))
    if match := _TAIL.match(band):
        return age >= int(match.group(1))
    if match := _UNDER.match(band):
        return age < int(match.group(1))
    raise ValueError(
        f"unrecognised age band {band!r}; write it as '20s', '50-59', '60+', "
        "'<40' or 'all_ages'"
    )


@dataclass(frozen=True, slots=True)
class Prevalence:
    """One condition's published rates, keyed the way its sources keyed them.

    ``by_sex`` is consulted before ``by_age`` and is populated only where a source
    actually reported a split. Hypertension has one at 18-39 and 40-59 and none at
    60+ ("not significantly different by sex"), and that asymmetry is reproduced
    rather than smoothed: inventing a split the source declined to report would be
    the same error as inventing a rate.
    """

    by_age: dict[str, Citation]
    by_sex: dict[str, dict[str, Citation]] | None = None

    def rate(self, age: int, sex: str) -> Citation | None:
        """The published rate for this applicant, or ``None`` if none was found.

        ``None`` is a real answer and the caller must handle it — see the module
        docstring. It means no source in note C reports this cell, not that the
        rate is zero.
        """
        if self.by_sex is not None and (bands := self.by_sex.get(sex)) is not None:
            for band, citation in bands.items():
                if band_contains(band, age):
                    return citation
        for band, citation in self.by_age.items():
            if band_contains(band, age):
                return citation
        return None


@dataclass(frozen=True, slots=True)
class ConditionSpec:
    """One drawable pre-existing condition and everything the sampler needs.

    ``body_parts`` empty means systemic — the condition is eligible for every case.
    A non-empty tuple means the condition is only eligible when the claim actually
    injures one of those regions, which is what keeps a lumbar-disc finding out of
    a wrist case: a degenerative finding nobody imaged is not a fact the file could
    ever contain.
    """

    key: str
    label: str
    body_system: BodySystem
    body_parts: tuple[str, ...]
    apportionment_targets: tuple[str, ...]
    """Regions this condition could actually be apportioned against.

    Not the same as ``body_parts``, which gates *eligibility*. Diabetes is systemic —
    eligible everywhere — but note C §2.5 documents it reaching only two regions, the
    wrist through the carpal-tunnel confound and the foot through polyneuropathy. So a
    diabetic applicant with a shoulder claim has a real condition that is nonetheless
    *wholly unrelated* to the claimed impairment, and that distinction is precisely
    what separates a thin apportionment argument from a baseless one.

    Empty means the condition reaches no claimed region at all — hypertension is the
    clean case, and it is always wholly unrelated.
    """
    icd10: str | None
    apportionment_basis: ApportionmentBasis
    asymptomatic_source: bool
    """Whether the prevalence table measured *asymptomatic* people.

    Load-bearing rather than bookkeeping. Escobedo turns on whether a nonindustrial
    factor was causing disability before the injury, and for every degenerative row
    below the source answers that directly: Brinjikji, Sher, Culvenor and Register all
    measured people with no symptoms. So the answer is read off the study rather than
    drawn from an invented coin.
    """
    mechanism: str
    """The one-line causal account a QME would give. Not rendered in M1 (M3 owns
    every document surface); carried here so the sampler and the eventual prose
    read from one table rather than two."""
    prevalence: Prevalence

    @property
    def systemic(self) -> bool:
        return not self.body_parts


# ---------------------------------------------------------------------------
# The catalog — note C sections 1, 2 and 3D
# ---------------------------------------------------------------------------

_BRINJIKJI = "Brinjikji et al. 2015, AJNR 36(4):811-816"
_JARRAYA = "Jarraya et al. 2018, Spine J (Framingham CT cohort), PMC6195485"
_NAKASHIMA = "Nakashima et al. 2015, Spine 40(6):392-398"
_SHER = "Sher et al. 1995, JBJS 77(1):10-15"
_CULVENOR = "Culvenor et al. 2019, Br J Sports Med 53(20):1268-1278"
_REGISTER = "Register et al. 2012, Am J Sports Med 40(12):2720-2724"
_NCHS_405 = "CDC/NCHS Data Brief No. 405, 2021 (NHANES 2017-2018)"
_NCHS_HTN = "CDC/NCHS, Hypertension Prevalence Aug 2021-Aug 2023"
_NHIS_2022 = "CDC/NCHS QuickStats, NHIS 2022 (diagnosed diabetes by age)"
_NHSR_213 = "CDC NHSR No. 213, Nov 2024"

CONDITION_CATALOG: dict[str, ConditionSpec] = {
    # -- systemic ----------------------------------------------------------
    "hypertension": ConditionSpec(
        key="hypertension",
        label="essential hypertension",
        body_system="cardiovascular",
        body_parts=(),
        apportionment_targets=(),
        icd10="I10",
        apportionment_basis="population_epidemiology",
        asymptomatic_source=False,
        mechanism=(
            "Chronically elevated arterial pressure, largely idiopathic and strongly "
            "age-graded, managed pharmacologically and unrelated to any occupational "
            "exposure in the ordinary case."
        ),
        prevalence=Prevalence(
            by_age={
                "18-39": Citation(0.234, _NCHS_HTN, "strong"),
                "40-59": Citation(0.525, _NCHS_HTN, "strong"),
                "60+": Citation(0.716, _NCHS_HTN, "strong"),
            },
            by_sex={
                # 60+ is deliberately absent from both sexes: the source reports
                # the rate as not significantly different there, so the pooled
                # by_age row is the honest answer for that band.
                "male": {
                    "18-39": Citation(0.300, _NCHS_HTN, "strong"),
                    "40-59": Citation(0.559, _NCHS_HTN, "strong"),
                },
                "female": {
                    "18-39": Citation(0.164, _NCHS_HTN, "strong"),
                    "40-59": Citation(0.490, _NCHS_HTN, "strong"),
                },
            },
        ),
    ),
    "diabetes": ConditionSpec(
        key="diabetes",
        label="type 2 diabetes mellitus",
        body_system="endocrine",
        body_parts=(),
        apportionment_targets=("wrist", "foot"),
        icd10="E11.9",
        apportionment_basis="population_epidemiology",
        asymptomatic_source=False,
        mechanism=(
            "Chronic hyperglycaemia causes microvascular ischaemia and direct glycation "
            "injury to peripheral nerve axons and connective tissue — the recognised "
            "nonindustrial confound behind an electrodiagnostic carpal-tunnel finding "
            "and a length-dependent sensorimotor polyneuropathy alike."
        ),
        prevalence=Prevalence(
            by_age={
                "18-34": Citation(0.013, _NHIS_2022, "strong"),
                # The source reports 13.3%-16.3% across urbanisation levels rather
                # than a point estimate; the midpoint is used and graded down to
                # `approximate` for exactly that reason.
                "45-64": Citation(
                    0.148, f"{_NHIS_2022} (13.3-16.3% range midpoint)", "approximate"
                ),
                "65+": Citation(0.201, _NHIS_2022, "strong"),
            }
        ),
    ),
    "depression_anxiety": ConditionSpec(
        key="depression_anxiety",
        label="depressive or anxiety disorder",
        body_system="psychiatric",
        body_parts=(),
        apportionment_targets=("psyche",),
        icd10="F41.9",
        apportionment_basis="population_epidemiology",
        asymptomatic_source=False,
        mechanism=(
            "A pre-existing mood or anxiety disorder predating the claim, which bears on "
            "a psychiatric add-on the way any nonindustrial contributor bears on a "
            "physical one — and is the reason the record must be read before a "
            "psychiatric component is treated as wholly industrial."
        ),
        prevalence=Prevalence(
            by_age={"all_ages": Citation(0.200, _NHSR_213, "strong")}
        ),
    ),
    "osteoporosis": ConditionSpec(
        key="osteoporosis",
        label="osteoporosis (low bone mineral density)",
        body_system="musculoskeletal",
        body_parts=("lumbar_spine", "thoracic_spine", "hip"),
        apportionment_targets=("lumbar_spine", "thoracic_spine", "hip"),
        icd10="M81.0",
        apportionment_basis="population_epidemiology",
        asymptomatic_source=False,
        mechanism=(
            "Postmenopausal oestrogen loss or gradual age-related osteopenia reduces bone "
            "mineral density below the fracture threshold, so vertebral bodies and femoral "
            "necks can fail under ordinary physiologic loads — a fragility fracture, as "
            "distinct from one produced by a discrete industrial mechanism."
        ),
        prevalence=Prevalence(
            by_age={},
            by_sex={
                "female": {
                    "50-64": Citation(0.131, _NCHS_405, "strong"),
                    "65+": Citation(0.271, _NCHS_405, "strong"),
                },
                "male": {
                    "50-64": Citation(0.033, _NCHS_405, "strong"),
                    "65+": Citation(0.057, _NCHS_405, "strong"),
                },
            },
        ),
    ),
    # -- degenerative, body-part gated -------------------------------------
    "lumbar_disc_degeneration": ConditionSpec(
        key="lumbar_disc_degeneration",
        label="lumbar degenerative disc disease",
        body_system="musculoskeletal",
        body_parts=("lumbar_spine",),
        apportionment_targets=("lumbar_spine",),
        icd10="M51.36",
        apportionment_basis="population_epidemiology",
        asymptomatic_source=True,
        mechanism=(
            "Disc desiccation and proteoglycan loss reduce disc hydration and height as a "
            "normal aging cascade, detectable from the third decade and near-universal by "
            "the seventh, independent of any single traumatic event."
        ),
        prevalence=Prevalence(
            by_age={
                "20s": Citation(0.37, _BRINJIKJI, "strong"),
                "30s": Citation(0.52, _BRINJIKJI, "strong"),
                "40s": Citation(0.68, _BRINJIKJI, "strong"),
                "50s": Citation(0.80, _BRINJIKJI, "strong"),
                "60s": Citation(0.88, _BRINJIKJI, "strong"),
                "70s": Citation(0.93, _BRINJIKJI, "strong"),
                "80s": Citation(0.96, _BRINJIKJI, "strong"),
            }
        ),
    ),
    "lumbar_facet_arthropathy": ConditionSpec(
        key="lumbar_facet_arthropathy",
        label="lumbar facet joint osteoarthritis",
        body_system="musculoskeletal",
        body_parts=("lumbar_spine",),
        apportionment_targets=("lumbar_spine",),
        icd10="M47.816",
        apportionment_basis="population_epidemiology",
        asymptomatic_source=True,
        mechanism=(
            "Facet joints are true synovial joints and undergo the same osteoarthritic "
            "cartilage cascade as any other joint, typically following and accelerated by "
            "disc-space narrowing at the same level."
        ),
        prevalence=Prevalence(
            by_age={},
            by_sex={
                "male": {
                    "40-59": Citation(0.44, _JARRAYA, "strong"),
                    "60-69": Citation(0.66, _JARRAYA, "strong"),
                    "70-89": Citation(0.86, _JARRAYA, "strong"),
                },
                "female": {
                    "40-59": Citation(0.56, _JARRAYA, "strong"),
                    "60-69": Citation(0.78, _JARRAYA, "strong"),
                    "70-89": Citation(0.83, _JARRAYA, "strong"),
                },
            },
        ),
    ),
    "cervical_disc_bulge": ConditionSpec(
        key="cervical_disc_bulge",
        label="cervical disc bulging",
        body_system="musculoskeletal",
        body_parts=("cervical_spine",),
        apportionment_targets=("cervical_spine",),
        icd10="M50.30",
        apportionment_basis="population_epidemiology",
        asymptomatic_source=True,
        mechanism=(
            "Cervical disc bulging is present in the large majority of wholly asymptomatic "
            "adults on MRI, so its presence on a post-injury study establishes nothing "
            "about causation on its own."
        ),
        prevalence=Prevalence(
            # Nakashima's full decade x finding table is paywalled; only the
            # aggregate was retrievable, so one all-ages row is what the source
            # supports. Grading it `single_study` rather than `strong` carries
            # that limitation with the number.
            by_age={"all_ages": Citation(0.876, _NAKASHIMA, "single_study")}
        ),
    ),
    "rotator_cuff_tear": ConditionSpec(
        key="rotator_cuff_tear",
        label="degenerative rotator cuff tear",
        body_system="musculoskeletal",
        body_parts=("shoulder",),
        apportionment_targets=("shoulder",),
        icd10="M75.100",
        apportionment_basis="population_epidemiology",
        asymptomatic_source=True,
        mechanism=(
            "The supraspinatus tendon has a hypovascular critical zone near its humeral "
            "insertion; with age that zone degenerates, thins and tears independent of "
            "trauma, and asymptomatic tears outnumber symptomatic ones."
        ),
        prevalence=Prevalence(
            by_age={
                "19-39": Citation(0.04, _SHER, "strong"),
                "40-60": Citation(0.28, _SHER, "strong"),
                "60+": Citation(0.54, _SHER, "strong"),
            }
        ),
    ),
    "knee_cartilage_defect": ConditionSpec(
        key="knee_cartilage_defect",
        label="knee cartilage defect",
        body_system="musculoskeletal",
        body_parts=("knee",),
        apportionment_targets=("knee",),
        icd10="M23.92",
        apportionment_basis="population_epidemiology",
        asymptomatic_source=True,
        mechanism=(
            "Cartilage breakdown from cumulative mechanical loading, worsened by body mass "
            "and biomechanical malalignment, occurring without any single traumatic event."
        ),
        prevalence=Prevalence(
            by_age={
                "<40": Citation(0.11, _CULVENOR, "strong"),
                "40+": Citation(0.43, _CULVENOR, "strong"),
            }
        ),
    ),
    "hip_labral_tear": ConditionSpec(
        key="hip_labral_tear",
        label="acetabular labral tear",
        body_system="musculoskeletal",
        body_parts=("hip",),
        apportionment_targets=("hip",),
        icd10="S73.191",
        apportionment_basis="population_epidemiology",
        asymptomatic_source=True,
        mechanism=(
            "Labral tearing is present in roughly two thirds of asymptomatic hips on MRI, "
            "with chondral and cystic change sharply more likely past the mid-thirties."
        ),
        prevalence=Prevalence(
            # N=45, ages 15-66, no decade stratification available. The small-N
            # caveat is the reason for the `single_study` grade rather than a
            # footnote somewhere else.
            by_age={
                "all_ages": Citation(
                    0.69, f"{_REGISTER} (N=45, no decade split)", "single_study"
                )
            }
        ),
    ),
}
"""Every condition the archetype sampler may draw, and the tables it is calibrated to.

Nine entries, each with a body system, an eligibility rule and a published rate
curve. The catalog is deliberately not the whole of note C: a condition earns a row
here only when a source in that note reports a prevalence the sampler can be held
to, because a condition with no target is a condition the marginal-matching test
cannot check.
"""


# ---------------------------------------------------------------------------
# Demographic draw targets
# ---------------------------------------------------------------------------

OBESITY_PREVALENCE: Prevalence = Prevalence(
    by_age={
        "20-39": Citation(0.355, "CDC/NCHS Data Brief No. 508, Sept 2024", "strong"),
        "40-59": Citation(0.464, "CDC/NCHS Data Brief No. 508, Sept 2024", "strong"),
        "60+": Citation(0.389, "CDC/NCHS Data Brief No. 508, Sept 2024", "strong"),
    }
)
"""BMI >= 30 by age band. Calibrates the ``obese`` + ``severely_obese`` union.

Obesity is a *risk factor* here rather than a drawn condition, which is the design
record's own line (§5: disease states are not profile fields). It is
``ApplicantProfile.bmi_band``, the archetype mixture conditions on it, and this
table is what that draw has to reproduce.
"""

SEVERE_SHARE_OF_OBESE: Knob = Knob(
    value=0.233,
    tag="measured",
    rationale=(
        "Severe obesity (BMI >= 40) is 9.4% of all adults against 40.3% for obesity "
        "overall in the same brief; 0.094/0.403 is the share of the obese population "
        "that is severely obese."
    ),
    source="CDC/NCHS Data Brief No. 508, Sept 2024 (both figures, same table)",
)

OVERWEIGHT_SHARE_OF_NON_OBESE: Knob = Knob(
    value=0.50,
    tag="invented",
    rationale=(
        "No overweight-versus-normal split appears anywhere in note C or note F. Half "
        "the non-obese remainder is a stated design choice, not a measurement, and is "
        "tagged accordingly rather than dressed up as a derivation from figures this "
        "package does not hold."
    ),
    source=(
        "Interview: of the applicants you see who are not obese, roughly how many "
        "would read as overweight rather than normal weight on a BMI chart?"
    ),
)

#: The applicant population the corpus-level knobs are calibrated against.
#:
#: A documentation rate quoted "across a caseload" is an expectation, and an expectation
#: needs a population. This is that population, written down rather than assumed — every
#: earlier attempt to hold a corpus-wide rate without one ended up holding it per
#: applicant instead, which is a different and unattainable claim.
#:
#: Ages mirror ``case_context._DERIVED_AGE_RANGE`` (25-62 inclusive, uniform), which is
#: the band the cast actually draws from, so this is a *derived* figure rather than an
#: independent guess. Sex follows :data:`FEMALE_SHARE`; body mass and smoking follow
#: their own tables at each age. Claim shapes are **invented** and tagged: no source
#: gives a distribution of body-part combinations across a caseload, and the seven
#: below are the one-and-two-region claims a real file tends to name, weighted toward
#: the single-region ones because that is what a caseload is mostly made of.
REFERENCE_AGES: tuple[int, ...] = tuple(range(25, 63))

REFERENCE_CLAIM_SHAPES: dict[tuple[str, ...], Knob] = {
    ("lumbar_spine",): Knob(
        value=0.26,
        tag="invented",
        rationale="The single most common industrial claim region.",
        source="Interview: what does the body-part mix across your caseload look like?",
    ),
    ("shoulder",): Knob(
        value=0.16, tag="invented", rationale="Single-region shoulder.", source="Interview."
    ),
    ("knee",): Knob(
        value=0.14, tag="invented", rationale="Single-region knee.", source="Interview."
    ),
    ("wrist",): Knob(
        value=0.10,
        tag="invented",
        rationale="Single-region wrist, the lightest of the common shapes.",
        source="Interview.",
    ),
    ("lumbar_spine", "shoulder"): Knob(
        value=0.16,
        tag="invented",
        rationale="The commonest two-region pairing.",
        source="Interview.",
    ),
    ("cervical_spine", "wrist"): Knob(
        value=0.10,
        tag="invented",
        rationale="Upper-limb-plus-neck, the repetitive-strain shape.",
        source="Interview.",
    ),
    ("hip", "knee"): Knob(
        value=0.08,
        tag="invented",
        rationale="Lower-limb pairing.",
        source="Interview.",
    ),
}
"""Claim shapes and their share of the reference caseload. Weights sum to 1.0."""


#: Ages below the youngest band CDC reports, and what is done about them.
#:
#: The obesity series starts at 20; the schema admits applicants from 16. Rather than
#: return ``None`` — which every other lookup here means as "no source, abstain" — the
#: BMI draw has to produce *something*, because every applicant has a body. So the
#: youngest reported band is reused, and that is an extrapolation rather than a
#: measurement. Named here so it is visible instead of buried in a branch.
BMI_YOUNGEST_REPORTED_BAND = "20-39"


def bmi_distribution(age: int) -> dict[str, float]:
    """P(BMI band | age) — the population the sampler draws from, in closed form.

    The same arithmetic ``medical_history._draw_bmi_band`` performs one applicant at a
    time, written out so the calibration can integrate over it. Two expressions of one
    distribution is a drift risk, so a test asserts the drawn cohort reproduces this
    table rather than trusting that they agree.

    Obesity is not sex-split in the source ("not significantly different"), so this is
    keyed on age alone.
    """
    severe, obese, overweight = bmi_band_cutoffs(age)
    return {
        "severely_obese": severe,
        "obese": obese - severe,
        "overweight": overweight,
        "normal_or_under": 1.0 - obese - overweight,
    }


def bmi_band_cutoffs(age: int) -> tuple[float, float, float]:
    """The three comparison values the BMI draw tests against, in its own order.

    ``(severe cutoff, obese cutoff, overweight remainder cutoff)``. Cutoffs rather than
    shares because a *cutoff* is what a draw is compared with, and in floating point
    those are not the same object: adding decomposed shares back up gives
    ``0.46399999999999997`` where the comparison this replaced used the source literal
    ``0.464``, and a draw of exactly that representable value lands in a different band
    depending on which one it meets. One in 2^53 draws, on a corpus that renders none
    of it — and still worth removing, because "identical" was claimed and was not true.

    So the arithmetic here is the original expression, character for character,
    including the subtraction order of the overweight test. :func:`bmi_distribution`
    derives its shares *from these cutoffs* rather than recomputing them, which is what
    keeps one definition rather than two that agree in exact arithmetic and disagree at
    the boundary.
    """
    citation = OBESITY_PREVALENCE.rate(age, "female")
    if citation is None:
        citation = OBESITY_PREVALENCE.by_age[BMI_YOUNGEST_REPORTED_BAND]
    obese_share = citation.value
    return (
        obese_share * SEVERE_SHARE_OF_OBESE.value,
        obese_share,
        (1.0 - obese_share) * OVERWEIGHT_SHARE_OF_NON_OBESE.value,
    )


def bmi_band_for_draw(draw: float, age: int) -> str:
    """Classify one uniform draw into a BMI band.

    The inverse CDF, written as the original chain of comparisons rather than as a
    cumulative walk. A cumulative walk is the obvious way to write this and is what
    introduced the boundary drift: ``severe + (obese - severe)`` is not ``obese``.
    """
    severe_cutoff, obese_cutoff, overweight_cutoff = bmi_band_cutoffs(age)
    if draw < severe_cutoff:
        return "severely_obese"
    if draw < obese_cutoff:
        return "obese"
    if draw - obese_cutoff < overweight_cutoff:
        return "overweight"
    return "normal_or_under"


@dataclass(frozen=True, slots=True)
class OddsRatio:
    """One band's odds ratio against its reference band, with its own provenance.

    Per band rather than per gradient, because a gradient is rarely uniform in how
    well it is known. The knee-cartilage curve is the case that forced this: 2.18 and
    2.63 are pooled figures from twenty-two studies, and 3.20 is a reading off a
    dose-response curve past its last published point. Tagging the whole gradient
    ``measured`` made the third number look like the first two.
    """

    value: float
    tag: Tag
    note: str = ""


@dataclass(frozen=True, slots=True)
class RiskGradient:
    """How one condition responds to body mass and smoking, relative to baseline.

    **Odds ratios, applied on the odds scale.** This is the correction review forced
    and it is not cosmetic. An odds ratio is a ratio of *odds*, and multiplying a
    probability by one does not preserve it — the error grows with baseline
    prevalence, which is exactly where these conditions live. Hypertension at 0.525 in
    the fifties times a 2.20 body-mass figure gives 1.155, an impossible probability
    that the clamp then quietly turned into 0.995. Applied properly,
    ``p' = OR*p / (1 - p + OR*p)``, it gives 0.709: still a large effect, and a
    real one.

    Two ratios combine by multiplying on the odds scale, which is the ordinary
    logistic assumption that log-odds contributions add. The transform runs *before*
    the population calibration, so the aggregate still lands on its cited marginal.

    **Every band is an odds ratio now, including the invented ones.** They could have
    stayed declared as probability multipliers and converted at the boundary; uniform
    is the better choice because two scales in one table is how the original error
    survived review in the first place. The invented magnitudes are unchanged — what
    changed is the claim being made about them, and they are tagged ``invented``
    either way.

    A ratio of 1.0 everywhere means **no source reports a gradient**, and flatness is
    then the honest answer rather than a missing feature. Four of the ten conditions
    are flat for exactly that reason — a count asserted by the flat-set guard rather
    than maintained by hand. The count this superseded said three of nine, and had
    been wrong about both numbers for as long as it existed.
    """

    bmi: dict[str, OddsRatio]
    smoking: dict[str, OddsRatio]
    tag: Tag
    rationale: str
    source: str

    def odds_ratio(self, bmi_band: str, smoking_status: str) -> float:
        """The combined odds ratio for one cell, against the reference cell."""
        bmi = self.bmi.get(bmi_band)
        smoking = self.smoking.get(smoking_status)
        return (1.0 if bmi is None else bmi.value) * (
            1.0 if smoking is None else smoking.value
        )

    def apply(self, probability: float, bmi_band: str, smoking_status: str) -> float:
        """*probability* moved onto this cell's odds, then back to a probability.

        The identity worth keeping in view: ``odds(apply(p)) == OR · odds(p)``. That
        is the property the tests assert, and it is the one plain multiplication does
        not have.
        """
        ratio = self.odds_ratio(bmi_band, smoking_status)
        if ratio == 1.0:
            return probability
        return ratio * probability / (1.0 - probability + ratio * probability)


_FLAT_BMI: dict[str, OddsRatio] = {
    band: OddsRatio(1.0, "measured", "no gradient reported") for band in BMI_BANDS
}
_FLAT_SMOKING: dict[str, OddsRatio] = {
    status: OddsRatio(1.0, "measured", "no gradient reported")
    for status in SMOKING_STATUSES
}


def _flat(reason: str) -> RiskGradient:
    return RiskGradient(
        bmi=dict(_FLAT_BMI),
        smoking=dict(_FLAT_SMOKING),
        tag="measured",
        rationale=f"Deliberately flat: {reason}",
        source="note C reports no BMI or smoking gradient for this condition",
    )


RISK_MULTIPLIERS: dict[str, RiskGradient] = {
    "lumbar_disc_degeneration": RiskGradient(
        bmi={
            "normal_or_under": OddsRatio(1.0, "measured", "the reference band"),
            "overweight": OddsRatio(1.30, "measured", "published OR, overweight"),
            "obese": OddsRatio(1.79, "measured", "published OR, obese"),
            "severely_obese": OddsRatio(
                1.79,
                "extrapolated",
                "the source does not split above BMI 30; the obese figure is held "
                "flat rather than extended, so this is a deliberately conservative "
                "extrapolation — the curve is very unlikely to be flat there",
            ),
        },
        smoking=dict(_FLAT_SMOKING),
        tag="measured",
        rationale=(
            "Odds ratios for the presence of lumbar disc degeneration: 1.30 overweight "
            "and 1.79 obese against normal BMI. Severe obesity reuses the obese figure "
            "because the source does not split above 30 — extending the curve past its "
            "last measured point would be extrapolation."
        ),
        source="Samartzis et al. 2012, Arthritis Rheum 64(5):1488-96 (PMC3571955)",
    ),
    "knee_cartilage_defect": RiskGradient(
        bmi={
            "normal_or_under": OddsRatio(1.0, "measured", "the reference band"),
            "overweight": OddsRatio(2.18, "measured", "pooled OR across 22 studies"),
            "obese": OddsRatio(2.63, "measured", "pooled OR across 22 studies"),
            "severely_obese": OddsRatio(
                3.20,
                "interpolated",
                "read off the dose-response curve between the pooled obese figure and "
                "the 4.7-5.7 relative risk the same meta-analysis reports at BMI 32.5 "
                "— inside the published range, but a reading rather than a reported "
                "point estimate",
            ),
        },
        smoking=dict(_FLAT_SMOKING),
        tag="measured",
        rationale=(
            "Pooled odds ratios 2.18 overweight and 2.63 obese against normal BMI, from "
            "22 studies. The severely-obese figure is the one interpolation here: the "
            "same meta-analysis reports relative risk climbing to 4.7-5.7 at BMI 32.5, "
            "so 3.20 is a conservative reading of a curve that is still rising."
        ),
        source="BMI/knee-OA dose-response meta-analysis, PMID 24990315, 2014",
    ),
    "diabetes": RiskGradient(
        bmi={
            "normal_or_under": OddsRatio(1.0, "invented", "the reference band"),
            "overweight": OddsRatio(1.40, "invented"),
            "obese": OddsRatio(2.50, "invented"),
            "severely_obese": OddsRatio(3.50, "invented"),
        },
        smoking={
            "never": OddsRatio(1.0, "invented", "the reference band"),
            "former": OddsRatio(1.05, "invented"),
            "current": OddsRatio(1.15, "invented"),
        },
        tag="invented",
        rationale=(
            "Note C carries obesity and diabetes prevalence separately and never joins "
            "them, so no odds ratio is available to cite. The *direction* is not in "
            "doubt — body mass is the dominant modifiable risk factor for type 2 "
            "diabetes — but these magnitudes are a design choice and are tagged as one "
            "rather than dressed up as a derivation."
        ),
        source=(
            "Interview: among the applicants you see with diabetes, how many would you "
            "describe as significantly overweight?"
        ),
    ),
    "hypertension": RiskGradient(
        bmi={
            "normal_or_under": OddsRatio(1.0, "invented", "the reference band"),
            "overweight": OddsRatio(1.30, "invented"),
            "obese": OddsRatio(1.80, "invented"),
            "severely_obese": OddsRatio(2.20, "invented"),
        },
        smoking={
            "never": OddsRatio(1.0, "invented", "the reference band"),
            "former": OddsRatio(1.05, "invented"),
            "current": OddsRatio(1.10, "invented"),
        },
        tag="invented",
        rationale=(
            "Same absence of a joined figure in note C as diabetes, same reasoning, "
            "smaller magnitudes — the body-mass association with hypertension is real "
            "and weaker than the diabetes one."
        ),
        source="Interview: same question as diabetes.",
    ),
    "osteoporosis": RiskGradient(
        bmi={
            # Inverted on purpose: low body mass is a *risk* for low bone density,
            # which is the one condition here where the gradient runs downhill.
            "normal_or_under": OddsRatio(1.0, "invented", "the reference band"),
            "overweight": OddsRatio(0.80, "invented"),
            "obese": OddsRatio(0.65, "invented"),
            "severely_obese": OddsRatio(0.60, "invented"),
        },
        smoking={
            "never": OddsRatio(1.0, "invented", "the reference band"),
            "former": OddsRatio(1.10, "invented"),
            "current": OddsRatio(1.40, "invented"),
        },
        tag="invented",
        rationale=(
            "Direction is textbook and note C supports neither magnitude: mechanical "
            "loading protects bone density, and smoking impairs it. The inverted BMI "
            "gradient is the reason this entry exists at all — a table where every "
            "multiplier ran the same way would encode 'heavier is worse' as a law."
        ),
        source=(
            "Interview: do you see osteoporosis argued more often in slighter "
            "applicants, and does a smoking history come up when it is?"
        ),
    ),
    "depression_anxiety": RiskGradient(
        bmi=dict(_FLAT_BMI),
        smoking={
            "never": OddsRatio(1.0, "invented", "the reference band"),
            "former": OddsRatio(1.10, "invented"),
            "current": OddsRatio(1.35, "invented"),
        },
        tag="invented",
        rationale=(
            "The smoking association is well established in direction and absent from "
            "note C in magnitude. BMI is left flat rather than guessed: the "
            "relationship is real but bidirectional, and a one-way multiplier would "
            "assert a causal direction nothing here supports."
        ),
        source="Interview: how often does a psych component travel with a smoking history?",
    ),
    "rotator_cuff_tear": _flat(
        "Tempelhof and Sher both report age curves only. Note C §2.4 names diabetes as "
        "an independent risk factor for asymptomatic cuff change, which is a "
        "condition-on-condition effect this layer does not yet model — flagged for M2 "
        "rather than approximated through BMI"
    ),
    "cervical_disc_bulge": _flat("Nakashima reports one aggregate rate and no covariates"),
    "lumbar_facet_arthropathy": _flat(
        "Jarraya isolates age and sex; the paper explicitly does not isolate BMI"
    ),
    "hip_labral_tear": _flat(
        "Register reports age and sex effects at N=45 and no body-mass association"
    ),
}
"""Within-marginal risk gradients — the reason the demographic fields exist.

Without these, every applicant of one age and sex carries identical risk whatever
their body mass or smoking status, and ``bmi_band`` becomes a field that is drawn,
stored and never consulted. Note C's surgical-clearance thresholds (§4.1 BMI 40, §4.2
HbA1c 7.7, §4.3 smoking cessation) are the downstream reason counsel wanted them: an
applicant refused a fusion for smoking is a different case from one who is not.

Six of the ten conditions carry a gradient; four are flat because their sources
report none. Two of the six are ``measured`` odds ratios; four are ``invented``
magnitudes whose *direction* is textbook, and the tag says which is which. The counts
are asserted by the flat-set guard in ``test_medical_history.py`` rather than
maintained here by hand — the sentence this replaced said "six of nine ... three are
flat" and had been wrong about the catalog's size since ``rotator_cuff_tear`` joined
it.
"""


SMOKING_DISTRIBUTION: dict[str, Knob] = {
    "never": Knob(
        0.60,
        "invented",
        "No smoking-prevalence figure appears in note C or note F — smoking enters "
        "note C only as a surgical-clearance threshold (§4.3), never as a base rate.",
        "Interview: across your caseload, roughly what share of applicants are current "
        "smokers, former smokers, and never-smokers?",
    ),
    "former": Knob(
        0.25,
        "invented",
        "Same absence of a source. The former/never split matters because note C §4.3 "
        "records that cessation of a year or more returns pseudarthrosis risk to the "
        "never-smoker baseline, so a former smoker is not a continuing apportionment "
        "target the way an active one is.",
        "Interview: same question as `never`.",
    ),
    "current": Knob(
        0.15,
        "invented",
        "Set above general-population current-smoking rates because WC claimant "
        "populations skew toward manual-labour occupations, per note C §3D's own "
        "caveat that general-population baselines likely undercount this cohort. The "
        "direction is reasoned; the magnitude is invented.",
        "Interview: same question as `never`.",
    ),
}
"""Smoking status, the purest ``invented`` knob in this module.

Kept as a knob table rather than three floats so the tag cannot be separated from
the number, and stated loudly because the alternative — a plausible-looking rate
with no source — is exactly what note C's NOT-FOUND discipline exists to refuse.
"""

FEMALE_SHARE: Knob = Knob(
    value=0.50,
    tag="invented",
    rationale=(
        "Neither research note carries a sex distribution for California WC claimants. "
        "An even split is the neutral choice; the real distribution is occupation-"
        "dependent and would need a WCIS pull this package does not have."
    ),
    source=(
        "Interview: across your caseload, is the applicant population close to an even "
        "split by sex, or does it skew with the industries you represent?"
    ),
)


# ---------------------------------------------------------------------------
# Documentation-visibility knobs (SME ruling 5)
# ---------------------------------------------------------------------------

P_SURFACES_IN_FILE: Knob = Knob(
    value=0.50,
    tag="counsel_confirmed",
    rationale=(
        "Counsel's answer to 'what share of applicants have at least one chronic "
        "condition that surfaces anywhere in the file' was, verbatim, 'one in two'. "
        "This is the DOCUMENTATION union — billing-coded plus narrative-mentioned — "
        "not true prevalence, and conflating the two is the error the two-surface gate "
        "exists to prevent. "
        "**Superseded upward from 0.33 on 2026-08-10.** The same question asked on "
        "2026-08-08 came back 'one in three'; asked again against the built model it "
        "came back 'one in two'. The later answer governs, and the revision is left "
        "visible rather than tidied away, because a knob that moved by half its own "
        "value on re-asking is a knob whose confidence grade should be read as an "
        "estimate — counsel's phrasing on the second pass was an estimate, not a "
        "figure read off anything."
    ),
    source=(
        "Alex (counsel), 2026-08-10 estimate, superseding 2026-08-08; "
        "sme-answers.md ruling 5"
    ),
)

P_BILLING_CODED: Knob = Knob(
    value=0.066,
    tag="measured",
    rationale=(
        "Comorbidity coded in the claim's own billing, trended from 0.024 in AY2000. "
        "The floor *inside* the surfacing union rather than a competing figure: NCCI's "
        "own brief says most claimants with a comorbidity are never diagnosed for it "
        "through the workers' compensation system. Unchanged when counsel revised the "
        "surfacing union on 2026-08-10, and deliberately so: this is a measurement of "
        "billing records and that is an expert's estimate of what a file mentions."
    ),
    source="NCCI, 'Comorbidities in Workers Compensation', Laws & Colon, Oct 2012",
)

P_ANY_CONDITION_MEASURED: Knob = Knob(
    value=0.76,
    tag="counsel_unconfirmed",
    rationale=(
        "True prevalence of at least one catalog condition, MEASURED OUT OF THIS "
        "ENGINE rather than asserted into it — see the finding below. Recorded so the "
        "documentation gate has an honest divisor and so the number can be argued "
        "with; it is an output of the calibration, not an input to it. It moved from "
        "0.71 to 0.76 when the archetype affinities were compressed to close the "
        "anti-fingerprint gap: every per-condition marginal still lands on its cited "
        "value, because the calibration re-solves, but a narrower spread puts less of "
        "the population's disease burden on a few heavily-loaded applicants and more "
        "of it on everyone, and P(at least one) is exactly the statistic that notices. "
        "That is the trade the compression buys, stated rather than hidden: an "
        "identifiable archetype is a worse defect in a synthetic corpus than an "
        "aggregate five points above where it sat."
    ),
    source=(
        "Measured over 21,000 sampled cases at derived ages across the seven realistic "
        "body-part shapes; pinned by test_medical_history.py's aggregate check."
    ),
)

P_ANY_CONDITION_EXPECTED: Knob = Knob(
    value=0.55,
    tag="counsel_unconfirmed",
    rationale=(
        "The design record's expected aggregate, KEPT AND FALSIFIED. Reproducing note "
        "C's per-condition marginals forces the aggregate to about 0.76, and the two "
        "cannot both hold: hypertension alone is a measured 0.525 at ages 40-59 and "
        "lumbar disc degeneration a measured 0.80 in the fifties, so any corpus that "
        "matches those rates has more than 55% of applicants carrying something. The "
        "0.55 was blended downward from all-adult baselines toward a working-age "
        "population; the blend was the weak step, not the per-condition figures. "
        "SME ruling 5 called this an aggregate *derived check* rather than an asserted "
        "knob, which is exactly the licence to report it moved rather than tune the "
        "sampler until it agreed. The consequence is confined and stated, and it has "
        "moved twice: at the old 0.33 surfacing union the squeeze implied file "
        "visibility near 43%, well under the design record's 60%. Counsel's 2026-08-10 "
        "revision to 0.50 puts it at 0.50 / 0.771 = **65%**, which no longer contradicts "
        "the design record at all — it slightly exceeds it. Worth saying plainly: the "
        "tension this note was written to record has largely dissolved, and what "
        "remains falsified is the 0.55 aggregate itself, not the visibility figure "
        "that followed from it. The surfacing union is held exactly regardless of "
        "either, because the documentation gate divides by the REFERENCE POPULATION's "
        "expected aggregate rather than by any one applicant's — see "
        ":func:`~wc_caseload_engine.medical_history.surfacing_conditional`. The "
        "distinction is not pedantry: dividing by the realised per-applicant figure is "
        "the form that could not reach its own target, and this note said so for a "
        "round while describing the arithmetic that replaced it."
    ),
    source=(
        "Interview: what share of applicants have a preexisting condition at all? The "
        "answer that would settle this is the true-prevalence question, not the "
        "already-answered documentation question."
    ),
)


# ---------------------------------------------------------------------------
# What this module knows it does not know
# ---------------------------------------------------------------------------

MIN_APPLICANT_AGE = 16
MAX_APPLICANT_AGE = 99
"""The range ``ApplicantProfile.age`` admits, and therefore the range the gap
inventory below has to account for. Mirrored here rather than imported because
:mod:`~wc_caseload_engine.seeds` imports this module, not the other way round; a
test pins the two together so the mirror cannot go stale.
"""


@dataclass(frozen=True, slots=True)
class CoverageGap:
    """One age range a condition's sources do not cover, named rather than filled.

    ``ages`` is machine-readable inclusive ranges rather than prose, so the
    completeness test can compare this inventory against the misses the lookup
    actually produces. A gap list written as English is a gap list nothing checks.
    """

    condition: str
    ages: tuple[tuple[int, int], ...]
    why: str

    def covers(self, age: int) -> bool:
        return any(low <= age <= high for low, high in self.ages)


KNOWN_COVERAGE_GAPS: tuple[CoverageGap, ...] = (
    CoverageGap(
        "hypertension",
        ((16, 17),),
        "The CDC series starts at 18. Applicants below it are rare, but the schema "
        "admits them, and a rate for a band the source excluded would be fabricated.",
    ),
    CoverageGap(
        "diabetes",
        ((16, 17), (35, 44)),
        "Two holes, one boundary and one interior. NHIS 2022's QuickStats bands are "
        "18-34, 45-64 and 65+; interpolating across 35-44 would invent a figure "
        "between 1.3% and 14.8% that nobody measured.",
    ),
    CoverageGap(
        "osteoporosis",
        ((16, 49),),
        "The NCHS brief reports adults 50 and over only. Osteoporosis below 50 is "
        "real but secondary, and a secondary cause is a case fact rather than an "
        "age-table lookup.",
    ),
    CoverageGap(
        "lumbar_disc_degeneration",
        ((16, 19), (90, 99)),
        "Brinjikji's decades run from the twenties to the eighties.",
    ),
    CoverageGap(
        "lumbar_facet_arthropathy",
        ((16, 39), (90, 99)),
        "Jarraya's Framingham CT cohort runs 40-89.",
    ),
    CoverageGap(
        "rotator_cuff_tear",
        ((16, 18),),
        "Sher's youngest band starts at 19.",
    ),
)
"""Every cell this module knows is missing, so the holes can be counted.

Written down because an unrecorded gap is indistinguishable from a bug: a sampler
that never gives a 38-year-old diabetes looks identical whether that is honest
abstention or a broken lookup. A test asserts this tuple is exactly the set of
misses :func:`age_band_rate` actually produces across the admissible age range, so
the list cannot quietly grow or go stale.
"""


def age_band_rate(condition: str, age: int, sex: str) -> Citation | None:
    """The published prevalence for one condition and applicant, or ``None``.

    ``None`` means no source in note C reports this cell — see
    :data:`KNOWN_COVERAGE_GAPS`. It is never a rate of zero, and a caller that
    treats it as one is asserting a measurement nobody made.
    """
    spec = CONDITION_CATALOG.get(condition)
    if spec is None:
        raise KeyError(
            f"unknown condition {condition!r}; the catalog holds "
            f"{sorted(CONDITION_CATALOG)}"
        )
    return spec.prevalence.rate(age, sex)


__all__ = [
    "BMI_BANDS",
    "BMI_YOUNGEST_REPORTED_BAND",
    "CONDITION_CATALOG",
    "FEMALE_SHARE",
    "KNOWN_COVERAGE_GAPS",
    "OBESE_BANDS",
    "OBESITY_PREVALENCE",
    "OVERWEIGHT_SHARE_OF_NON_OBESE",
    "P_ANY_CONDITION_EXPECTED",
    "P_ANY_CONDITION_MEASURED",
    "P_BILLING_CODED",
    "P_SURFACES_IN_FILE",
    "RISK_MULTIPLIERS",
    "SEVERE_SHARE_OF_OBESE",
    "SEXES",
    "SMOKING_DISTRIBUTION",
    "SMOKING_STATUSES",
    "ApportionmentBasis",
    "BmiBand",
    "BodySystem",
    "Citation",
    "ConditionSpec",
    "Confidence",
    "CoverageGap",
    "Knob",
    "Prevalence",
    "RiskGradient",
    "Sex",
    "SmokingStatus",
    "Tag",
    "age_band_rate",
    "band_contains",
    "bmi_distribution",
]
