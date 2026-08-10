"""AJC-60 — the world-truth ledger, its sampler, and the gate that holds it shut.

Four claims are under test here, and they fail in different directions on purpose.

**The gate moves no bytes.** A seed with no ``scenario.medical_history`` block must
generate exactly what it generated before the block existed, and a seed *with* one
must still move no rendered byte in M1, because nothing renders the ledger yet. The
first half is back-compat; the second is the M3 tripwire.

**The marginals reproduce their sources.** The sampler is calibrated rather than
hand-tuned, so this is a real invariant rather than a fixture: change an archetype
affinity and the marginals must still land, because the scale re-solves.

**Profile membership is not recoverable.** Within-profile variation is mandatory, and
"mandatory" has to mean something a test can fail on.

**The published unions are the counsel-confirmed ones.** One applicant in three
surfaces a comorbidity; 6.6% carry one in billing.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pytest

from conftest import requires_substrate
from wc_caseload_engine.case_context import applicant_date_of_birth
from wc_caseload_engine.clinical_grounding import (
    BMI_BANDS,
    CONDITION_CATALOG,
    KNOWN_COVERAGE_GAPS,
    MAX_APPLICANT_AGE,
    MIN_APPLICANT_AGE,
    OBESE_BANDS,
    P_ANY_CONDITION_EXPECTED,
    P_ANY_CONDITION_MEASURED,
    P_BILLING_CODED,
    P_SURFACES_IN_FILE,
    SEXES,
    SMOKING_STATUSES,
    age_band_rate,
    band_contains,
)
from wc_caseload_engine.manifests import CASE_FACTS_NAME, MANIFEST_NAME, generate_case
from wc_caseload_engine.medical_history import (
    _P_CEILING,
    _P_FLOOR,
    HEALTH_ARCHETYPES,
    _rng,
    archetype_weights,
    calibrate,
    condition_probabilities,
    derive_medical_history,
    eligible_conditions,
    probability_of_any_condition,
)
from wc_caseload_engine.planner import build_case_plan
from wc_caseload_engine.seeds import ANCHOR_DATE, ApplicantProfile, parse_case_seed

# ---------------------------------------------------------------------------
# Cohort machinery
# ---------------------------------------------------------------------------

#: Every region the catalog gates a degenerative finding on, so one cohort case is
#: eligible for every condition at once. Deliberately unrealistic — a real claim names
#: one or two regions — because a marginal is only checkable on cases where the
#: condition could have been drawn at all.
ALL_GATED_PARTS: tuple[str, ...] = (
    "lumbar_spine",
    "cervical_spine",
    "shoulder",
    "knee",
    "hip",
)

#: Body-part sets a real caseload actually carries, for the aggregate checks.
REALISTIC_PART_SETS: tuple[tuple[str, ...], ...] = (
    ("lumbar_spine",),
    ("shoulder",),
    ("knee",),
    ("lumbar_spine", "shoulder"),
    ("cervical_spine", "wrist"),
    ("hip", "knee"),
    ("wrist",),
)

#: Samples per (age, sex) cell in the marginal test.
#:
#: Chosen from the binomial standard error, not picked round. At ``p = 0.5`` — the
#: worst case — one cell's realised rate has ``sd = sqrt(0.25/2500) = 0.010``, so the
#: 0.035 tolerance below is 3.5 sigma. The test is *deterministic* (fixed rng seeds),
#: so this is not a flake budget: it is how far the fixed realisation is permitted to
#: sit from its source before the calibration is called wrong. A real calibration
#: break — a mis-solved scale, an affinity that stopped being scaled — moves a
#: marginal by tenths, not hundredths, so the gap between 0.035 and "actually broken"
#: is two orders of magnitude wide.
COHORT_N = 2500

#: The measured worst-case deviation is 0.015 across every cell; see the module
#: docstring of ``clinical_grounding`` for where the targets come from.
MARGINAL_TOLERANCE = 0.035


def _seed_body(
    rng_seed: int,
    parts: tuple[str, ...] = ALL_GATED_PARTS,
    scenario: dict[str, Any] | None = None,
    applicant: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "case_id": f"TC-{rng_seed % 900 + 100}",
        "rng_seed": rng_seed,
        "profile": {"applicant": applicant or {}},
        "injury": {
            "type": "specific",
            "date_of_injury": "2022-04-11",
            "body_parts": [{"part": part} for part in parts],
        },
        "scenario": {"medical_history": scenario if scenario is not None else {}},
    }


def _sample(
    count: int,
    *,
    base: int,
    parts: tuple[str, ...] = ALL_GATED_PARTS,
    applicant: dict[str, Any] | None = None,
    scenario: dict[str, Any] | None = None,
) -> list[Any]:
    """A cohort of ledgers, drawn through the real derivation.

    Deliberately not through ``generate_case``: the sampler is what is under test,
    and rendering 2,500 cases to measure a proportion would trade half an hour for no
    additional evidence about the draw.
    """
    out = []
    for index in range(count):
        seed = parse_case_seed(
            _seed_body(base + index, parts, scenario=scenario, applicant=applicant)
        )
        out.append(
            derive_medical_history(seed, None, date_of_birth=applicant_date_of_birth(seed))
        )
    return out


# ---------------------------------------------------------------------------
# The grounding tables
# ---------------------------------------------------------------------------


class TestTheGroundingTablesAreHonest:
    def test_the_declared_age_range_matches_the_schema(self) -> None:
        """The mirror in ``clinical_grounding`` cannot go stale silently."""
        age = ApplicantProfile.model_fields["age"]
        bounds = {
            type(item).__name__: getattr(item, "ge", None) or getattr(item, "le", None)
            for item in age.metadata
        }
        assert bounds.get("Ge") == MIN_APPLICANT_AGE
        assert bounds.get("Le") == MAX_APPLICANT_AGE

    def test_every_coverage_gap_is_real_and_every_real_gap_is_declared(self) -> None:
        """The NOT-FOUND inventory, checked against the lookup that produces it.

        An unrecorded gap is indistinguishable from a bug: a sampler that never gives
        a 38-year-old diabetes looks identical whether that is honest abstention or a
        broken table. So the inventory is compared in *both* directions — a declared
        gap that is not real is a stale note, and a real gap that is not declared is a
        hole nobody counted.
        """
        declared: dict[str, set[int]] = defaultdict(set)
        for gap in KNOWN_COVERAGE_GAPS:
            assert gap.condition in CONDITION_CATALOG, f"{gap.condition} is not a condition"
            assert gap.why.strip(), f"{gap.condition} declares a gap with no reason"
            for age in range(MIN_APPLICANT_AGE, MAX_APPLICANT_AGE + 1):
                if gap.covers(age):
                    declared[gap.condition].add(age)

        measured: dict[str, set[int]] = defaultdict(set)
        for key in CONDITION_CATALOG:
            for age in range(MIN_APPLICANT_AGE, MAX_APPLICANT_AGE + 1):
                for sex in SEXES:
                    if age_band_rate(key, age, sex) is None:
                        measured[key].add(age)

        undeclared = {k: sorted(v - declared[k]) for k, v in measured.items() if v - declared[k]}
        unreal = {k: sorted(v - measured[k]) for k, v in declared.items() if v - measured[k]}
        assert dict(declared) == dict(measured), (
            "KNOWN_COVERAGE_GAPS and the lookup disagree. Real gaps missing from the "
            f"inventory: {undeclared}; declared but not real: {unreal}"
        )

    def test_no_value_travels_without_its_provenance(self) -> None:
        for key, spec in CONDITION_CATALOG.items():
            assert spec.mechanism.strip(), f"{key} has no mechanism"
            cited = list(spec.prevalence.by_age.values())
            for bands in (spec.prevalence.by_sex or {}).values():
                cited.extend(bands.values())
            assert cited, f"{key} has no published rate at all"
            for citation in cited:
                assert citation.source.strip(), f"{key} carries a value with no source"
                assert 0.0 < citation.value <= 1.0, f"{key}: {citation.value} is not a rate"

    @pytest.mark.parametrize(
        ("band", "age", "expected"),
        [
            ("20s", 20, True),
            ("20s", 29, True),
            ("20s", 30, False),
            ("50-59", 50, True),
            ("50-59", 59, True),
            ("50-59", 60, False),
            ("60+", 60, True),
            ("60+", 59, False),
            ("<40", 39, True),
            ("<40", 40, False),
            ("all_ages", 16, True),
        ],
    )
    def test_band_boundaries_are_inclusive_where_their_sources_are(
        self, band: str, age: int, expected: bool
    ) -> None:
        assert band_contains(band, age) is expected

    def test_an_unrecognised_band_raises_rather_than_reading_as_a_miss(self) -> None:
        """A silent ``False`` would turn a typo into a fabricated coverage gap."""
        with pytest.raises(ValueError, match="unrecognised age band"):
            band_contains("40 to 59", 45)


# ---------------------------------------------------------------------------
# The calibration
# ---------------------------------------------------------------------------


class TestTheCalibrationSolves:
    def test_the_mixture_hits_its_target_for_every_reachable_cell(self) -> None:
        """The solve, checked analytically before any sampling happens.

        Sampling can only ever measure this to within a standard error; the solve
        itself is exact, so the exact version is asserted first. A failure here says
        the calibration is broken; a failure in the cohort test with this one green
        says the *draw* is.
        """
        checked = 0
        for key in CONDITION_CATALOG:
            for age in (18, 25, 35, 45, 55, 65, 75, 85):
                for sex in SEXES:
                    citation = age_band_rate(key, age, sex)
                    if citation is None:
                        continue
                    for bmi in BMI_BANDS:
                        for smoking in SMOKING_STATUSES:
                            weights = archetype_weights(age, bmi, smoking)
                            probabilities = dict(
                                condition_probabilities(key, age, sex, bmi, smoking)
                            )
                            realised = sum(
                                weights[name] * probabilities[name] for name in weights
                            )
                            assert realised == pytest.approx(citation.value, abs=1e-9), (
                                f"{key} at age {age}, {sex}, {bmi}, {smoking}: the "
                                f"mixture yields {realised}, its source says "
                                f"{citation.value}"
                            )
                            checked += 1
        assert checked > 500, f"only {checked} cells exercised; the sweep has shrunk"

    def test_a_target_outside_the_probability_bounds_is_refused(self) -> None:
        """Clamping silently would leave a marginal wrong by an amount nothing reports."""
        weights = tuple(sorted(archetype_weights(45, "obese", "never").items()))
        with pytest.raises(ValueError, match="outside the archetype probability bounds"):
            calibrate("hypertension", weights, 0.999)

    def test_every_archetype_can_produce_every_condition(self) -> None:
        """The anti-fingerprint guarantee, at its source rather than in the corpus.

        The bound asserted is the **floor**, not merely "greater than zero", and the
        mutation gate is why. The first version of this guard asked for
        ``0 < p < 1``, which is satisfied with the floor deleted — ``scale * affinity``
        is a product of positives and never actually reaches zero. m17-4 survived it.

        That was the guard failing to cover its own fix, and the distinction it missed
        is the whole point: a probability of one in a million is not zero, but an
        archetype carrying one is *effectively* excludable, which is exactly the
        recoverability the floor exists to prevent. So the floor itself is the
        assertion.
        """
        for key in CONDITION_CATALOG:
            for age in (25, 45, 70):
                for sex in SEXES:
                    if age_band_rate(key, age, sex) is None:
                        continue
                    probabilities = condition_probabilities(key, age, sex, "obese", "current")
                    assert probabilities, f"{key} has no probabilities at all"
                    assert {name for name, _ in probabilities} == set(HEALTH_ARCHETYPES)
                    for name, probability in probabilities:
                        assert _P_FLOOR <= probability <= _P_CEILING, (
                            f"{key}/{name} is {probability}, outside "
                            f"[{_P_FLOOR}, {_P_CEILING}] — an archetype whose "
                            "probability approaches zero can be ruled out by observing "
                            "the condition, which makes membership recoverable"
                        )

    def test_archetype_weights_are_a_distribution(self) -> None:
        for age in (20, 40, 60, 80):
            for bmi in BMI_BANDS:
                for smoking in SMOKING_STATUSES:
                    weights = archetype_weights(age, bmi, smoking)
                    assert set(weights) == set(HEALTH_ARCHETYPES)
                    assert sum(weights.values()) == pytest.approx(1.0)
                    assert all(w > 0 for w in weights.values())

    def test_the_demographic_steer_does_something(self) -> None:
        """Anti-vacuity: steers that changed nothing would make the mixture a constant."""
        lean = archetype_weights(45, "normal_or_under", "never")
        heavy = archetype_weights(45, "severely_obese", "current")
        assert heavy["metabolic"] > lean["metabolic"] * 2
        assert heavy["resilient"] < lean["resilient"] / 2
        young = archetype_weights(25, "overweight", "never")
        old = archetype_weights(75, "overweight", "never")
        assert old["degenerative"] > young["degenerative"] * 2


# ---------------------------------------------------------------------------
# The marginal-matching invariant
# ---------------------------------------------------------------------------


class TestTheCorpusReproducesItsSources:
    """Gate 2. The claim the whole `c-calibrated-by-b` decision rests on."""

    @pytest.mark.parametrize("age", [25, 45, 68])
    @pytest.mark.parametrize("sex", list(SEXES))
    def test_per_condition_marginals_match_the_cited_tables(self, age: int, sex: str) -> None:
        cohort = _sample(
            COHORT_N, base=7_000_000 + age * 100, applicant={"age": age, "sex": sex}
        )
        realised_age = cohort[0].demographics.age
        counts = Counter(c.key for history in cohort for c in history.conditions)

        checked = 0
        for key in CONDITION_CATALOG:
            citation = age_band_rate(key, realised_age, sex)
            if citation is None:
                assert counts[key] == 0, (
                    f"{key} was drawn {counts[key]} times at age {realised_age} where "
                    "no source reports a rate — a NOT-FOUND cell must produce nothing, "
                    "not a guess"
                )
                continue
            realised = counts[key] / COHORT_N
            sigma = math.sqrt(citation.value * (1 - citation.value) / COHORT_N)
            assert abs(realised - citation.value) <= MARGINAL_TOLERANCE, (
                f"{key} at age {realised_age}/{sex}: corpus gives {realised:.4f}, "
                f"{citation.source} gives {citation.value:.4f} "
                f"({abs(realised - citation.value) / max(sigma, 1e-9):.1f} sigma)"
            )
            checked += 1
        assert checked >= 5, f"only {checked} conditions were checkable; the cohort shrank"

    def test_the_marginal_check_can_fail(self) -> None:
        """Anti-vacuity. A tolerance wide enough to accept anything proves nothing.

        The control perturbs the *target*, not the corpus: if a table entry moved by
        a tenth and the assertion still passed, the assertion would not be measuring
        the corpus against its source at all.
        """
        cohort = _sample(600, base=7_900_000, applicant={"age": 45, "sex": "female"})
        counts = Counter(c.key for history in cohort for c in history.conditions)
        realised = counts["hypertension"] / 600
        citation = age_band_rate("hypertension", 45, "female")
        assert citation is not None
        assert abs(realised - citation.value) <= MARGINAL_TOLERANCE
        assert abs(realised - (citation.value + 0.15)) > MARGINAL_TOLERANCE, (
            "a target 15 points away still passed the tolerance; the marginal "
            "assertion cannot distinguish a calibrated corpus from an uncalibrated one"
        )


# ---------------------------------------------------------------------------
# Anti-fingerprint
# ---------------------------------------------------------------------------


#: How far the archetype posterior may go before a condition set is a giveaway.
#:
#: Measured at 0.934, on ``{diabetes, hypertension, lumbar_disc_degeneration}`` —
#: which is the *metabolic* profile almost by definition, and a corpus where that
#: combination did **not** point at metabolic burden would be the unrealistic one. The
#: bound is set above the measurement rather than at it because the quantity under
#: control is "no set is a certainty", not "no set is informative": a fingerprint is a
#: deterministic identifier, and evidence is not.
MAX_ARCHETYPE_POSTERIOR = 0.97

#: Occurrences a condition set needs before its archetype spread means anything.
#:
#: One observation of a set cannot testify to uniqueness. This is why the cohort below
#: is large: the structural guarantee is that every archetype *can* produce every set,
#: and a rare set drawn twenty times will look degenerate long before it looks like
#: what it is.
MIN_SET_SUPPORT = 20


class TestProfileMembershipIsNotAFingerprint:
    """Gate 3. Within-profile variation is mandatory, so it has to be falsifiable.

    Two claims, and they are genuinely different strengths.

    The **structural** one — every archetype can produce every condition — is exact
    and is asserted analytically in ``TestTheCalibrationSolves``. No chain of observed
    conditions can rule an archetype out, because no probability is ever zero.

    The **empirical** one below is weaker on purpose, because the strong version is
    false for any sampler and would be wrong to want. Conditions really are evidence
    about a health profile: someone carrying diabetes and hypertension really is more
    likely to be metabolically burdened, and a corpus that hid that would be less
    realistic, not more. What must not exist is a set that *settles* the question.

    **Cohort shape is load-bearing.** These run over the one-and-two-region claims a
    caseload actually contains. An artificial case naming all five gated regions makes
    almost every applicant comorbid, so the sparse tail — nobody with anything — comes
    back attributable to ``resilient`` alone. That is an artifact of a case shape the
    corpus does not contain, and measuring the property on it would fail the sampler
    for a claim nobody makes.

    **What M4 adds.** The leakage anti-probe there makes the claim this one cannot:
    that a classifier trained on the *analyzer-visible artifacts* — rendered documents,
    manifests, document counts — cannot recover the archetype better than chance. That
    probe needs artifacts, and in M1 there are deliberately none, because nothing about
    this ledger reaches any output at all. It also covers the leak this test structurally
    cannot see: a correlation between profile and something the renderer varies, such as
    document count or section length, which is note F's standing warning.
    """

    def test_no_well_supported_condition_set_belongs_to_one_archetype(self) -> None:
        cohort: list[Any] = []
        for index, parts in enumerate(REALISTIC_PART_SETS):
            cohort.extend(_sample(3000, base=8_000_000 + index * 10_000, parts=parts))

        by_set: dict[frozenset[str], Counter[str]] = defaultdict(Counter)
        for history in cohort:
            by_set[history.condition_keys()][history.archetype] += 1
        supported = {
            key: spread
            for key, spread in by_set.items()
            if sum(spread.values()) >= MIN_SET_SUPPORT
        }
        assert len(supported) >= 20, (
            f"only {len(supported)} sets reached support {MIN_SET_SUPPORT}; the cohort "
            "is too small for this assertion to mean anything"
        )
        covered = sum(sum(s.values()) for s in supported.values()) / len(cohort)
        assert covered > 0.90, (
            f"supported sets cover only {covered:.1%} of the corpus, so the probe is "
            "reading the tail rather than the corpus"
        )

        singleton = {
            tuple(sorted(key)): dict(spread)
            for key, spread in supported.items()
            if len(spread) == 1
        }
        assert not singleton, (
            f"condition sets produced by exactly one archetype despite appearing "
            f"{MIN_SET_SUPPORT}+ times: {dict(list(singleton.items())[:5])} — profile "
            "membership is recoverable outright from the conditions"
        )

    def test_no_condition_set_makes_an_archetype_a_near_certainty(self) -> None:
        """The quantitative half: informative is fine, decisive is not."""
        cohort: list[Any] = []
        for index, parts in enumerate(REALISTIC_PART_SETS):
            cohort.extend(_sample(3000, base=8_000_000 + index * 10_000, parts=parts))
        by_set: dict[frozenset[str], Counter[str]] = defaultdict(Counter)
        for history in cohort:
            by_set[history.condition_keys()][history.archetype] += 1

        worst_key: tuple[str, ...] = ()
        worst = 0.0
        for key, spread in by_set.items():
            total = sum(spread.values())
            if total < MIN_SET_SUPPORT:
                continue
            posterior = max(spread.values()) / total
            if posterior > worst:
                worst, worst_key = posterior, tuple(sorted(key))
        assert worst <= MAX_ARCHETYPE_POSTERIOR, (
            f"{worst_key} identifies its archetype with posterior {worst:.3f}; a "
            "condition set that settles the profile is a fingerprint"
        )

    def test_within_profile_variation_actually_fires(self) -> None:
        """The other half: overlap is worthless if each profile emits one fixed set."""
        cohort = _sample(4000, base=8_100_000, parts=("lumbar_spine", "shoulder"))
        per_archetype: dict[str, set[frozenset[str]]] = defaultdict(set)
        for history in cohort:
            per_archetype[history.archetype].add(history.condition_keys())
        assert set(per_archetype) == set(HEALTH_ARCHETYPES), (
            f"only {sorted(per_archetype)} were ever drawn; an unreachable archetype "
            "is a fingerprint of a different kind"
        )
        for archetype, sets in per_archetype.items():
            assert len(sets) >= 8, (
                f"{archetype} produced only {len(sets)} distinct condition sets — "
                "membership would be readable off the conditions"
            )

    def test_every_archetype_can_produce_a_healthy_applicant(self) -> None:
        """Including ``multimorbid``. A profile that always emits something is a tell."""
        cohort = _sample(6000, base=8_200_000, parts=("lumbar_spine",))
        empty = {h.archetype for h in cohort if not h.conditions}
        assert set(empty) == set(HEALTH_ARCHETYPES), (
            f"archetypes that never produced a condition-free applicant: "
            f"{sorted(set(HEALTH_ARCHETYPES) - empty)}"
        )


# ---------------------------------------------------------------------------
# The two-surface documentation gate
# ---------------------------------------------------------------------------


class TestTheDocumentationGate:
    """Gate: the two published unions, held at the applicant level."""

    def test_the_surfacing_and_billing_unions_are_the_counsel_confirmed_ones(self) -> None:
        cohort: list[Any] = []
        for index, parts in enumerate(REALISTIC_PART_SETS):
            cohort.extend(_sample(2000, base=9_000_000 + index * 10_000, parts=parts))
        total = len(cohort)
        surfaced = sum(1 for h in cohort if any(c.surfaces_in_file for c in h.conditions))
        billed = sum(1 for h in cohort if any(c.billing_coded for c in h.conditions))

        assert surfaced / total == pytest.approx(P_SURFACES_IN_FILE.value, abs=0.02), (
            f"{surfaced / total:.4f} of applicants surface a comorbidity; counsel "
            f"confirmed {P_SURFACES_IN_FILE.value}"
        )
        assert billed / total == pytest.approx(P_BILLING_CODED.value, abs=0.01), (
            f"{billed / total:.4f} carry one in billing; NCCI measured "
            f"{P_BILLING_CODED.value}"
        )

    def test_billing_coded_never_escapes_the_surfacing_union(self) -> None:
        """The measured 6.6% is a floor *inside* the 0.33, not a competing figure."""
        cohort = _sample(3000, base=9_500_000)
        for history in cohort:
            for condition in history.conditions:
                if condition.billing_coded:
                    assert condition.surfaces_in_file, (
                        f"{condition.key} is billing-coded but does not surface — the "
                        "billing floor has escaped the union it sits inside"
                    )

    def test_the_true_prevalence_is_higher_than_the_documented_one(self) -> None:
        """The finding, pinned so it cannot drift back unnoticed.

        Note C's per-condition marginals force an aggregate near 0.71, not the 0.55
        the design record expected. SME ruling 5 made the aggregate a *derived check*
        rather than an asserted knob, which is the licence to report it moved instead
        of tuning the sampler until it agreed. Both numbers are asserted: the one that
        holds, and the one that does not.
        """
        cohort: list[Any] = []
        for index, parts in enumerate(REALISTIC_PART_SETS):
            cohort.extend(_sample(1500, base=9_600_000 + index * 10_000, parts=parts))
        realised = sum(1 for h in cohort if h.conditions) / len(cohort)

        assert realised == pytest.approx(P_ANY_CONDITION_MEASURED.value, abs=0.03), (
            f"aggregate true prevalence is now {realised:.4f}; "
            f"P_ANY_CONDITION_MEASURED records {P_ANY_CONDITION_MEASURED.value}"
        )
        assert realised > P_ANY_CONDITION_EXPECTED.value + 0.05, (
            "the aggregate has come back down to the design record's 0.55. If the "
            "per-condition marginals still match their sources, this is a genuine "
            "discovery and P_ANY_CONDITION_EXPECTED's falsification note is now wrong"
        )

    def test_the_analytic_and_realised_prevalence_agree(self) -> None:
        """The documentation gate divides by the analytic figure, so it has to be right."""
        cohort = _sample(3000, base=9_700_000, parts=("lumbar_spine", "shoulder"))
        analytic = sum(
            probability_of_any_condition(
                h.demographics.age,
                h.demographics.sex,
                h.demographics.bmi_band,
                h.demographics.smoking_status,
                frozenset({"lumbar_spine", "shoulder"}),
            )
            for h in cohort
        ) / len(cohort)
        realised = sum(1 for h in cohort if h.conditions) / len(cohort)
        assert analytic == pytest.approx(realised, abs=0.02), (
            f"analytic P(any)={analytic:.4f} but the draw yields {realised:.4f}; the "
            "gate is dividing by a number the sampler does not honour"
        )


# ---------------------------------------------------------------------------
# Demographics
# ---------------------------------------------------------------------------


class TestDemographics:
    def test_age_comes_from_the_anchor_and_never_from_a_clock(self) -> None:
        for stated in (22, 39, 57, 71):
            seed = parse_case_seed(_seed_body(4242, applicant={"age": stated}))
            history = derive_medical_history(
                seed, None, date_of_birth=applicant_date_of_birth(seed)
            )
            assert history is not None
            assert history.demographics.age in (stated - 1, stated), (
                f"stated age {stated} became {history.demographics.age}"
            )

    def test_the_ledger_and_the_cast_agree_about_the_applicants_age(self) -> None:
        """Two derivations of one fact is the defect the ledger pattern removes."""
        seed = parse_case_seed(_seed_body(515, applicant={"age": 48}))
        plan = build_case_plan(seed)
        assert plan.medical_history is not None
        born = plan.cast.case.applicant.date_of_birth
        expected = (
            ANCHOR_DATE.year
            - born.year
            - ((ANCHOR_DATE.month, ANCHOR_DATE.day) < (born.month, born.day))
        )
        assert plan.medical_history.demographics.age == expected

    def test_a_stated_demographic_wins_over_the_draw(self) -> None:
        stated = {"sex": "female", "bmi_band": "severely_obese", "smoking_status": "current"}
        seed = parse_case_seed(_seed_body(606, applicant=stated))
        history = derive_medical_history(
            seed, None, date_of_birth=applicant_date_of_birth(seed)
        )
        assert history is not None
        assert history.demographics.sex == "female"
        assert history.demographics.bmi_band == "severely_obese"
        assert history.demographics.smoking_status == "current"
        assert history.demographics.obese

    def test_the_bmi_draw_reproduces_the_cited_obesity_prevalence(self) -> None:
        for age, target in ((30, 0.355), (50, 0.464), (70, 0.389)):
            cohort = _sample(2500, base=10_000_000 + age * 100, applicant={"age": age})
            obese = sum(1 for h in cohort if h.demographics.bmi_band in OBESE_BANDS)
            assert obese / 2500 == pytest.approx(target, abs=0.035), (
                f"age {age}: {obese / 2500:.3f} obese against CDC's {target}"
            )

    def test_every_demographic_value_is_reachable(self) -> None:
        cohort = _sample(2000, base=10_500_000)
        assert {h.demographics.sex for h in cohort} == set(SEXES)
        assert {h.demographics.bmi_band for h in cohort} == set(BMI_BANDS)
        assert {h.demographics.smoking_status for h in cohort} == set(SMOKING_STATUSES)


# ---------------------------------------------------------------------------
# The seed gate and its schema
# ---------------------------------------------------------------------------


class TestTheSeedGate:
    def test_an_absent_block_derives_no_ledger_at_all(self) -> None:
        """``None``, not an empty ledger — the distinction the whole gate rests on."""
        seed = parse_case_seed(
            {
                "case_id": "TC-700",
                "rng_seed": 77,
                "injury": {
                    "type": "specific",
                    "date_of_injury": "2022-04-11",
                    "body_parts": [{"part": "lumbar_spine"}],
                },
            }
        )
        assert seed.scenario.medical_history is None
        assert derive_medical_history(seed, None) is None
        assert build_case_plan(seed).medical_history is None

    def test_a_present_block_derives_one(self) -> None:
        seed = parse_case_seed(_seed_body(78))
        plan = build_case_plan(seed)
        assert plan.medical_history is not None
        assert plan.medical_history.archetype in HEALTH_ARCHETYPES

    def test_sample_conditions_false_keeps_only_what_the_author_stated(self) -> None:
        scenario = {
            "sample_conditions": False,
            "conditions": [
                {
                    "label": "invasive ductal carcinoma, right breast",
                    "body_system": "oncologic",
                    "body_part": None,
                    "wholly_unrelated": True,
                    "severity": "moderate",
                    "symptomatic_before_doi": True,
                }
            ],
        }
        history = _sample(1, base=800, scenario=scenario)[0]
        assert [c.label for c in history.conditions] == [
            "invasive ductal carcinoma, right breast"
        ]
        assert history.conditions[0].wholly_unrelated
        assert history.conditions[0].key == "seeded"

    def test_a_stated_condition_is_never_drawn_a_second_time(self) -> None:
        scenario = {
            "conditions": [{"label": "essential hypertension", "key": "hypertension"}]
        }
        for history in _sample(200, base=810, scenario=scenario):
            keys = [c.key for c in history.conditions]
            assert keys.count("hypertension") == 1, (
                f"hypertension appears {keys.count('hypertension')} times — a stated "
                "condition was drawn again under a second id"
            )

    def test_a_pinned_archetype_is_the_one_used(self) -> None:
        for name in HEALTH_ARCHETYPES:
            history = _sample(1, base=820, scenario={"archetype": name})[0]
            assert history.archetype == name

    def test_wholly_unrelated_follows_the_claims_own_regions(self) -> None:
        """Diabetes reaches the wrist and the foot; it reaches nothing else.

        The distinction that separates a thin apportionment argument from a baseless
        one, so it is asserted on the two sides of the same condition.
        """
        wrist = _sample(
            400, base=830, parts=("wrist",), scenario={"conditions": [
                {"label": "type 2 diabetes mellitus", "key": "diabetes"}
            ]}
        )
        shoulder = _sample(
            400, base=830, parts=("shoulder",), scenario={"conditions": [
                {"label": "type 2 diabetes mellitus", "key": "diabetes"}
            ]}
        )
        assert all(
            not c.wholly_unrelated
            for h in wrist
            for c in h.conditions
            if c.key == "diabetes"
        )
        assert all(
            c.wholly_unrelated
            for h in shoulder
            for c in h.conditions
            if c.key == "diabetes"
        )

    def test_hypertension_is_always_wholly_unrelated(self) -> None:
        for history in _sample(300, base=840):
            for condition in history.conditions:
                if condition.key == "hypertension":
                    assert condition.wholly_unrelated

    def test_a_degenerative_finding_needs_its_region_on_the_claim(self) -> None:
        for history in _sample(400, base=850, parts=("wrist",)):
            for condition in history.conditions:
                spec = CONDITION_CATALOG[condition.key]
                assert spec.systemic, (
                    f"{condition.key} was drawn on a wrist-only claim, but it is gated "
                    f"on {spec.body_parts}"
                )

    def test_eligibility_is_the_catalogs_own_gate(self) -> None:
        assert "lumbar_disc_degeneration" in eligible_conditions(frozenset({"lumbar_spine"}))
        assert "lumbar_disc_degeneration" not in eligible_conditions(frozenset({"wrist"}))
        assert "hypertension" in eligible_conditions(frozenset({"wrist"}))

    def test_an_incidental_finding_carries_no_onset_and_no_prior_symptoms(self) -> None:
        """Read off the study rather than drawn: those cohorts were asymptomatic."""
        for history in _sample(300, base=860):
            for condition in history.conditions:
                spec = CONDITION_CATALOG[condition.key]
                if spec.asymptomatic_source:
                    assert condition.onset is None
                    assert condition.symptomatic_before_doi is False
                else:
                    assert condition.onset is not None
                    assert condition.symptomatic_before_doi is True

    def test_a_derived_onset_precedes_the_injury(self) -> None:
        for history in _sample(300, base=870):
            for condition in history.conditions:
                if condition.onset is not None:
                    assert condition.onset < ANCHOR_DATE


class TestTheSchemaRejectsIncoherentInput:
    def test_an_unknown_catalog_key_is_refused(self) -> None:
        with pytest.raises(Exception, match="not a grounding-catalog condition"):
            parse_case_seed(
                _seed_body(880, scenario={"conditions": [{"label": "x", "key": "gout"}]})
            )

    def test_an_award_for_a_region_the_claim_never_named_is_refused(self) -> None:
        with pytest.raises(Exception, match="does not overlap the claim's own body_parts"):
            parse_case_seed(
                _seed_body(
                    881,
                    scenario={
                        "prior_claims": [
                            {
                                "body_parts": ["lumbar_spine"],
                                "date_of_injury": "2015-01-05",
                                "resolution_type": "stipulated_award",
                                "award": {
                                    "body_parts": ["knee"],
                                    "pd_percent": 12,
                                    "award_date": "2016-02-01",
                                },
                            }
                        ]
                    },
                )
            )

    def test_a_claim_cannot_resolve_before_it_arises(self) -> None:
        with pytest.raises(Exception, match="precedes its own date_of_injury"):
            parse_case_seed(
                _seed_body(
                    882,
                    scenario={
                        "prior_claims": [
                            {
                                "body_parts": ["lumbar_spine"],
                                "date_of_injury": "2015-01-05",
                                "resolution_date": "2014-01-05",
                                "resolution_type": "c_and_r",
                            }
                        ]
                    },
                )
            )

    def test_an_award_cannot_precede_its_injury(self) -> None:
        with pytest.raises(Exception, match="precedes the claim's date_of_injury"):
            parse_case_seed(
                _seed_body(
                    883,
                    scenario={
                        "prior_claims": [
                            {
                                "body_parts": ["lumbar_spine"],
                                "date_of_injury": "2015-01-05",
                                "resolution_type": "stipulated_award",
                                "award": {
                                    "body_parts": ["lumbar_spine"],
                                    "pd_percent": 12,
                                    "award_date": "2014-02-01",
                                },
                            }
                        ]
                    },
                )
            )

    def test_a_pinned_archetype_with_nothing_to_draw_is_refused(self) -> None:
        with pytest.raises(Exception, match="nothing draws from it"):
            parse_case_seed(
                _seed_body(
                    884, scenario={"archetype": "metabolic", "sample_conditions": False}
                )
            )

    def test_the_conservative_c_and_r_default_is_opt_in(self) -> None:
        """§2-Q7. Defaulting the permissive way would bake an unreviewed reading in."""
        seed = parse_case_seed(
            _seed_body(
                885,
                scenario={
                    "prior_claims": [
                        {
                            "body_parts": ["lumbar_spine"],
                            "date_of_injury": "2015-01-05",
                            "resolution_type": "c_and_r",
                            "award": {
                                "body_parts": ["lumbar_spine"],
                                "pd_percent": 20,
                                "award_date": "2016-02-01",
                                "resolution_type": "c_and_r",
                            },
                        }
                    ]
                },
            )
        )
        history = derive_medical_history(
            seed, None, date_of_birth=applicant_date_of_birth(seed)
        )
        assert history is not None
        award = history.awards[0]
        assert award.still_exists_conclusively_presumed is False
        assert award.pd_percent == 20
        assert award.body_parts == ("lumbar_spine",)


class TestUngroundedDoctrineHooksWarnAndDoNotBlock:
    """§2-Q2: an explicit control wins, and it wins loudly."""

    def _plan(self, hooks: list[str], scenario: dict[str, Any] | None) -> Any:
        body = _seed_body(890, scenario=scenario)
        if scenario is None:
            body["scenario"] = {}
        body["lifecycle"] = {
            "target_stage": "pre_trial",
            "eval_type": "qme",
            "doctrine_hooks": hooks,
        }
        body["injury"]["date_of_injury"] = "2020-04-11"
        return build_case_plan(parse_case_seed(body))

    def test_an_ungrounded_hook_warns(self) -> None:
        plan = self._plan(["lc4664_prior_award"], {})
        assert any("lc4664_prior_award" in w and "world-truth ledger" in w for w in plan.warnings)

    def test_a_grounded_hook_is_silent(self) -> None:
        plan = self._plan(
            ["lc4664_prior_award"],
            {
                "prior_claims": [
                    {
                        "body_parts": ["lumbar_spine"],
                        "date_of_injury": "2015-01-05",
                        "resolution_type": "stipulated_award",
                        "award": {
                            "body_parts": ["lumbar_spine"],
                            "pd_percent": 12,
                            "award_date": "2016-02-01",
                        },
                    }
                ]
            },
        )
        assert not any("world-truth ledger" in w for w in plan.warnings)

    def test_the_hook_is_kept_rather_than_stripped(self) -> None:
        plan = self._plan(["lc4664_prior_award"], {})
        assert "lc4664_prior_award" in plan.seed.lifecycle.doctrine_hooks

    def test_a_seed_with_no_medical_history_block_is_never_warned(self) -> None:
        """The warning is a manifest byte, and absent has to move zero of them."""
        plan = self._plan(["lc4664_prior_award"], None)
        assert plan.medical_history is None
        assert not any("world-truth ledger" in w for w in plan.warnings)


# ---------------------------------------------------------------------------
# Byte inertness — the back-compat instrument
# ---------------------------------------------------------------------------


def _tree(directory: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(directory)): path.read_bytes()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


@requires_substrate
class TestTheLedgerMovesNoBytes:
    """Gate 1, at case scope. ``golden_gate.py --check`` is the corpus-scope half."""

    def _generate(self, out: Path, scenario: dict[str, Any] | None) -> dict[str, bytes]:
        body = {
            "case_id": "TC-650",
            "rng_seed": 31337,
            "injury": {
                "type": "specific",
                "date_of_injury": "2022-04-11",
                "body_parts": [{"part": "lumbar_spine"}, {"part": "shoulder"}],
            },
            "lifecycle": {"target_stage": "medical_legal", "eval_type": "qme"},
            "documents": {"format_mix": {"pdf": 1.0}},
            "output": {"formats": ["pdf"]},
        }
        if scenario is not None:
            body["scenario"] = {"medical_history": scenario}
        generate_case(parse_case_seed(body), out, case_number=1)
        return _tree(out)

    def test_a_present_block_changes_nothing_but_the_seed(self, tmp_path: Path) -> None:
        """The M3 tripwire.

        Everything the ledger holds is byte-inert today, so opting in must move
        exactly one file: ``seed.yaml``, which is the input and is *supposed* to
        differ. The moment M3 renders a past-medical-history section this goes red,
        which is the signal to delete the ``not yet honoured`` marker from the gate's
        docstring — the edit that otherwise gets forgotten.
        """
        without = self._generate(tmp_path / "without", None)
        with_block = self._generate(tmp_path / "with", {})

        assert set(without) == set(with_block), "opting in changed the file tree's shape"
        moved = sorted(name for name in without if without[name] != with_block[name])
        assert moved == ["TC-650/manifest.json", "TC-650/seed.yaml"], (
            f"opting into scenario.medical_history moved {moved}; only the seed and "
            "the hash of the seed may differ while nothing renders the ledger"
        )

        # Two files may move, and exactly one reason is admissible for each. The seed
        # is the input and is *supposed* to differ. The manifest records a hash of
        # that input, so it follows — but nothing else in it may, and asserting the
        # whole manifest minus one key is what keeps "only the seed changed" from
        # quietly covering a published ledger field.
        before = json.loads(without["TC-650/manifest.json"])
        after = json.loads(with_block["TC-650/manifest.json"])
        assert before["provenance"].pop("seedHash") != after["provenance"].pop("seedHash")
        assert before == after, (
            "the manifest moved for a reason other than the seed's own hash — "
            "something about the medical-history ledger has reached a published "
            "artifact"
        )
        assert without["TC-650/case_facts.yaml"] == with_block["TC-650/case_facts.yaml"]

    def test_the_ledger_reaches_neither_published_copy(self, tmp_path: Path) -> None:
        """World truth in the manifest would collapse the two-level design.

        A document could then cite the ledger directly, and a party's assertion about
        the history could no longer diverge from the history — which is the entire
        point of having two levels. M4 opens a scorer-only channel; the analyzer-
        visible artifacts never carry it.
        """
        self._generate(tmp_path / "with", {})
        case = tmp_path / "with" / "TC-650"
        manifest = json.loads((case / MANIFEST_NAME).read_text(encoding="utf-8"))
        facts = (case / CASE_FACTS_NAME).read_text(encoding="utf-8")

        assert "medicalHistory" not in json.dumps(manifest)
        assert "archetype" not in json.dumps(manifest).lower()
        assert "medical_history" not in facts
        assert "archetype" not in facts
        for term in ("hypertension", "bmiBand", "smokingStatus"):
            assert term not in json.dumps(manifest), f"{term} reached the manifest"

    def test_the_probe_can_see_a_change_at_all(self, tmp_path: Path) -> None:
        """Anti-vacuity: a comparison that never differs would pass everything."""
        plain = self._generate(tmp_path / "plain", None)
        seeded = self._generate(tmp_path / "seeded", {"conditions": [{"label": "x"}]})
        assert plain != seeded, "the tree comparison cannot detect a seed change"


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_the_same_seed_derives_the_same_ledger(self) -> None:
        seed = parse_case_seed(_seed_body(24680))
        first = derive_medical_history(seed, None, date_of_birth=applicant_date_of_birth(seed))
        second = derive_medical_history(seed, None, date_of_birth=applicant_date_of_birth(seed))
        assert first == second

    def test_the_new_streams_do_not_disturb_an_existing_draw(self) -> None:
        """R2, the standing rng-drift risk, asserted rather than trusted.

        The ledger draws from a ``medical:`` namespace nothing else uses. If a salt
        collided with ``facts:`` or with the cast's bare salts, the case's clinical
        ledger would move the moment the medical block was opted into — and it would
        move silently, because nothing renders the medical block to give it away.
        """
        without = build_case_plan(
            parse_case_seed(
                {
                    "case_id": "TC-651",
                    "rng_seed": 909,
                    "injury": {
                        "type": "specific",
                        "date_of_injury": "2022-04-11",
                        "body_parts": [{"part": "lumbar_spine"}],
                    },
                }
            )
        )
        with_block = build_case_plan(parse_case_seed(_seed_body(909, ("lumbar_spine",))))
        assert without.case_facts == with_block.case_facts
        assert (
            without.cast.case.applicant.full_name == with_block.cast.case.applicant.full_name
        )
        assert (
            without.cast.case.applicant.date_of_birth
            == with_block.cast.case.applicant.date_of_birth
        )
        assert [d.subtype for d in without.documents] == [
            d.subtype for d in with_block.documents
        ]
        assert [d.doc_date for d in without.documents] == [
            d.doc_date for d in with_block.documents
        ]

    #: Every salt the medical layer draws on, and the cast salts it must avoid.
    MEDICAL_SALTS = (
        "sex",
        "bmi",
        "smoking",
        "archetype",
        "conditions",
        "condition_detail",
        "documentation",
    )
    CAST_SALTS = ("dob", "carrier", "applicant_firm", "defense_firm", "")

    def test_every_medical_stream_is_its_own(self) -> None:
        """R2, stated as the risk that actually exists here.

        Two earlier attempts at this guard measured the wrong thing, and both are
        worth recording because the correction is the finding.

        The first asserted that opting into the medical layer disturbs no existing
        draw. m17-5 survived it — and had to, because every stream is a fresh
        ``random.Random``. Two generators seeded independently cannot interfere
        however their salts are chosen, so that assertion was true by construction.

        The second asserted that sex is not a function of the date of birth. Also
        survivable: the map from ``rng_seed`` to a date of birth is not injective, so
        two applicants can share a birthday from different seeds and differ in sex
        even when both draws come off one salt.

        What salting actually buys is **stream separation**, and that is what is
        asserted here: no two medical draws share a stream, and no medical draw shares
        a stream with the cast. Collapse them and every demographic moves together —
        sex, body mass, smoking and the archetype all decided by one number, which is
        the correlated-attribute tell note F warns about — and a medical salt landing
        on a cast salt would make the ledger a readable shadow of the applicant's own
        identity.
        """
        seed = parse_case_seed(_seed_body(40_000))
        medical = {salt: _rng(seed, salt).random() for salt in self.MEDICAL_SALTS}
        assert len(set(medical.values())) == len(self.MEDICAL_SALTS), (
            f"two medical streams produced the same first draw: {medical} — the "
            "layer's draws are collapsed onto one stream and every demographic moves "
            "together"
        )

        cast = {salt: seed.rng(salt).random() for salt in self.CAST_SALTS}
        collisions = {
            (m_salt, c_salt)
            for m_salt, value in medical.items()
            for c_salt, other in cast.items()
            if value == other
        }
        assert not collisions, (
            f"medical streams collide with the cast's own: {sorted(collisions)} — the "
            "ledger would be a readable shadow of the applicant's identity"
        )

    def test_the_stream_probe_can_detect_a_collision(self) -> None:
        """Anti-vacuity: the comparison above must be able to see a shared stream."""
        seed = parse_case_seed(_seed_body(40_001))
        assert _rng(seed, "sex").random() == _rng(seed, "sex").random(), (
            "the same salt gave two different draws, so the probe cannot recognise a "
            "collision even when one is in front of it"
        )

    def test_a_different_seed_reaches_a_different_ledger(self) -> None:
        """Anti-vacuity for the two assertions above."""
        histories = {
            (*sorted(h.condition_keys()), h.archetype)
            for h in _sample(60, base=30_000)
        }
        assert len(histories) > 10, "the sampler is producing one answer for every seed"
