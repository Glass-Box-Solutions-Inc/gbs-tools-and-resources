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
import pkgutil
import random
from collections import Counter, defaultdict
from datetime import timedelta
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from conftest import requires_substrate
from wc_caseload_engine.case_context import DERIVED_AGE_RANGE, applicant_date_of_birth
from wc_caseload_engine.clinical_grounding import (
    BMI_BANDS,
    CONDITION_CATALOG,
    FEMALE_SHARE,
    KNOWN_COVERAGE_GAPS,
    MAX_APPLICANT_AGE,
    MIN_APPLICANT_AGE,
    OBESE_BANDS,
    OBESITY_PREVALENCE,
    OVERWEIGHT_SHARE_OF_NON_OBESE,
    P_ANY_CONDITION_EXPECTED,
    P_ANY_CONDITION_MEASURED,
    P_BILLING_CODED,
    P_SURFACES_IN_FILE,
    REFERENCE_CLAIM_SHAPES,
    RISK_MULTIPLIERS,
    SEVERE_SHARE_OF_OBESE,
    SEXES,
    SMOKING_DISTRIBUTION,
    SMOKING_STATUSES,
    age_band_rate,
    band_contains,
    bmi_band_cutoffs,
    bmi_band_for_draw,
    bmi_distribution,
)
from wc_caseload_engine.manifests import CASE_FACTS_NAME, MANIFEST_NAME, generate_case
from wc_caseload_engine.medical_history import (
    _INTERCEPT_BOUND,
    _P_CEILING,
    _P_FLOOR,
    HEALTH_ARCHETYPES,
    HOOK_GROUNDING,
    SIBTF_DISABLING_SEVERITIES,
    SIBTF_QUALIFYING,
    MedicalCondition,
    _apply_documentation_gate,
    _baseline,
    _clamped,
    _graded,
    _logistic,
    _rng,
    archetype_weights,
    billing_conditional,
    calibrate,
    condition_probabilities,
    derive_medical_history,
    eligible_conditions,
    expected_any_condition,
    probability_of_any_condition,
    reference_age_weights,
    sibtf_requirement,
    surfacing_conditional,
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

#: Samples drawn per claim shape by the aggregate cross-check.
#:
#: Round 6, finding 1. Named rather than inline because
#: :data:`~wc_caseload_engine.clinical_grounding.P_ANY_CONDITION_MEASURED` states the
#: plan it was measured under, and a stated number nothing computes is a number that
#: drifts: it claimed 21,000 cases while the probe drew 10,500. The knob's provenance
#: is asserted against these constants below, so the prose cannot move without the
#: arithmetic moving with it.
AGGREGATE_PROBE_PER_SHAPE = 1500

#: How the cross-check weights claim shapes: **equally**, one block per shape.
#:
#: Deliberately *not* the reference population's weighting. ``REFERENCE_CLAIM_SHAPES``
#: leans toward single-region claims because that is what a caseload is mostly made of,
#: and ``expected_any_condition()`` integrates over those weights — which is why the
#: analytic figure is 0.771 and this sampled one is near 0.76. Two different populations
#: honestly reported, rather than one number asked to be both.
AGGREGATE_PROBE_WEIGHTING = "equal per shape"

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

#: Total cases the aggregate cross-check draws. Computed, never typed.
AGGREGATE_PROBE_N = AGGREGATE_PROBE_PER_SHAPE * len(REALISTIC_PART_SETS)

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


def _cell_rate(condition: str, age: int, sex: str, bmi: str, smoking: str) -> float:
    """The realised probability for one applicant cell, mixture-weighted."""
    weights = archetype_weights(age, bmi, smoking)
    probabilities = dict(condition_probabilities(condition, age, sex, bmi, smoking))
    return sum(weights[name] * probabilities[name] for name in weights)


def _profile_rate(
    condition: str, age: int, sex: str, bmi: str, smoking: str, archetype: str
) -> float:
    """One archetype's own probability, with the mixture held out of it.

    Two independent things move risk across BMI bands: the **steer**, which shifts
    the archetype mixture toward the metabolic and degenerative profiles as body mass
    rises, and the **multiplier**, which raises that profile's own risk. A mixture
    reading cannot tell them apart, and m17-8 proved it — flattening every risk
    multiplier to 1.0 left ``_cell_rate``'s gradient standing on the steer alone,
    comfortably past the ratio the mixture test asserts.

    So the multiplier gets a reading of its own. Weights do not appear here, which is
    exactly what makes it a clean instrument.
    """
    return dict(condition_probabilities(condition, age, sex, bmi, smoking))[archetype]


def _population_rate(condition: str, age: int, sex: str) -> float:
    """The cell rates integrated over the population the sampler actually draws."""
    smoking = {status: knob.value for status, knob in SMOKING_DISTRIBUTION.items()}
    return sum(
        bmi_share * smoke_share * _cell_rate(condition, age, sex, band, status)
        for band, bmi_share in bmi_distribution(age).items()
        for status, smoke_share in smoking.items()
    )


class TestTheCalibrationSolves:
    def test_the_population_hits_its_target_for_every_reachable_age(self) -> None:
        """The solve, checked analytically before any sampling happens.

        What is pinned is the **population aggregate**, not each cell. The first
        version of this guard asserted per-cell equality and passed — which was the
        defect, not the proof: solving per cell made every cell hit the marginal
        exactly and cancelled every risk gradient underneath it. Review caught that the
        assertion and the bug were the same statement.

        Sampling can only measure this to within a standard error; the solve is exact,
        so the exact version is asserted first. A failure here says the calibration is
        broken; a failure in the cohort test with this one green says the *draw* is.
        """
        checked = 0
        for key in CONDITION_CATALOG:
            for age in (18, 25, 35, 45, 55, 65, 75, 85):
                for sex in SEXES:
                    citation = age_band_rate(key, age, sex)
                    if citation is None:
                        continue
                    realised = _population_rate(key, age, sex)
                    assert realised == pytest.approx(citation.value, abs=1e-9), (
                        f"{key} at age {age}, {sex}: the population yields {realised}, "
                        f"its source says {citation.value}"
                    )
                    checked += 1
        assert checked > 60, f"only {checked} cells exercised; the sweep has shrunk"

    def test_a_target_outside_the_probability_bounds_is_refused(self) -> None:
        """Clamping silently would leave a marginal wrong by an amount nothing reports."""
        with pytest.raises(ValueError, match="outside the archetype probability bounds"):
            calibrate("hypertension", 45, 0.999)


class TestRiskGradientsSurviveCalibration:
    """Finding 1. The demographic fields have to *do* something.

    Solving the scale per demographic cell made every cell reproduce the age/sex
    marginal exactly — which sounds like success and is the opposite. A severely obese
    current smoker and a normal-weight never-smoker of the same age came out with
    identical diabetes risk, so ``bmi_band`` and ``smoking_status`` were drawn, stored,
    and never consulted by anything. The fields exist because those differences are
    real and because note C's surgical-clearance thresholds (§4.1 BMI 40, §4.2 HbA1c,
    §4.3 smoking cessation) turn on them downstream.

    So both halves are asserted together, and they are in tension by design: the
    gradient must be visible *and* the population aggregate must still land on its
    citation. Either alone is satisfiable by a wrong implementation.
    """

    GRADED = (
        ("diabetes", 45, "female"),
        ("hypertension", 45, "male"),
        ("lumbar_disc_degeneration", 45, "female"),
        ("knee_cartilage_defect", 45, "male"),
    )

    @pytest.mark.parametrize(("condition", "age", "sex"), GRADED)
    def test_body_mass_moves_the_risk_within_a_single_profile(
        self, condition: str, age: int, sex: str
    ) -> None:
        """The multiplier on its own, with the archetype mixture held out.

        This is the assertion that actually guards ``RISK_MULTIPLIERS``. The mixture
        reading below cannot: flattening every multiplier to 1.0 leaves the archetype
        *steer* producing a gradient of its own, and it clears the ratio the mixture
        test asks for. m17-8 survived on exactly that, which is the whole reason two
        readings exist where one looked sufficient.
        """
        rates = {
            band: _profile_rate(condition, age, sex, band, "never", "resilient")
            for band in BMI_BANDS
        }
        ordered = [rates[band] for band in BMI_BANDS]
        assert ordered == sorted(ordered), (
            f"{condition}: within one profile, risk does not rise with body mass — "
            f"{rates}. The archetype mixture is not involved here, so this is the "
            "risk multiplier itself"
        )
        assert rates["severely_obese"] > rates["normal_or_under"] * 1.25, (
            f"{condition}: holding the profile fixed, the severely obese cell is only "
            f"{rates['severely_obese'] / rates['normal_or_under']:.2f}x the "
            "normal-weight one — the documented multiplier is doing nothing"
        )

    @pytest.mark.parametrize(("condition", "age", "sex"), GRADED)
    def test_body_mass_moves_the_risk_it_is_documented_to_move(
        self, condition: str, age: int, sex: str
    ) -> None:
        """The gradient a reader of the corpus would actually see.

        Both channels together — the steer moving the mixture and the multiplier
        moving each profile's own risk. Kept because it is the reader-visible claim,
        and separated from the one above because a compound reading cannot attribute
        what it measures.
        """
        rates = {
            band: _cell_rate(condition, age, sex, band, "never") for band in BMI_BANDS
        }
        ordered = [rates[band] for band in BMI_BANDS]
        assert ordered == sorted(ordered), (
            f"{condition}: risk does not rise monotonically with body mass — {rates}"
        )
        assert rates["severely_obese"] > rates["normal_or_under"] * 1.25, (
            f"{condition}: the severely obese cell is only "
            f"{rates['severely_obese'] / rates['normal_or_under']:.2f}x the "
            "normal-weight cell, which is not a gradient a reader would notice"
        )

    def test_the_one_condition_whose_gradient_runs_downhill(self) -> None:
        """Osteoporosis. A table where every multiplier ran the same way would encode
        "heavier is worse" as a law, so the inverted case is asserted explicitly."""
        light = _cell_rate("osteoporosis", 68, "female", "normal_or_under", "never")
        heavy = _cell_rate("osteoporosis", 68, "female", "severely_obese", "never")
        assert light > heavy, (
            f"osteoporosis risk is {heavy:.4f} in the severely obese cell against "
            f"{light:.4f} in the normal-weight one; mechanical loading protects bone "
            "density and this gradient has been flattened or inverted"
        )

    SMOKING_GRADED = (
        ("depression_anxiety", 45, "female"),
        ("osteoporosis", 68, "female"),
        ("diabetes", 45, "male"),
    )

    @pytest.mark.parametrize(("condition", "age", "sex"), SMOKING_GRADED)
    def test_smoking_moves_the_risk_within_a_single_profile(
        self, condition: str, age: int, sex: str
    ) -> None:
        """The smoking half of the same correction, and it needed it separately.

        Fixing the BMI reading did not fix this one: the smoking assertions were still
        reading ``_cell_rate``, so flattening only the smoking ratios left all three
        of them green on the archetype steer alone. Two mechanisms, two readings — the
        pattern has to be applied per gradient, not per module.
        """
        never = _profile_rate(condition, age, sex, "overweight", "never", "resilient")
        current = _profile_rate(condition, age, sex, "overweight", "current", "resilient")
        assert current > never, (
            f"{condition}: holding the profile fixed, current smokers are at "
            f"{current:.5f} against {never:.5f} for never-smokers — the documented "
            "smoking ratio is doing nothing"
        )

    def test_smoking_moves_the_risks_it_is_documented_to_move(self) -> None:
        """The mixture reading, kept for the same reason as its BMI counterpart."""
        for condition, age, sex in self.SMOKING_GRADED:
            never = _cell_rate(condition, age, sex, "overweight", "never")
            current = _cell_rate(condition, age, sex, "overweight", "current")
            assert current > never, (
                f"{condition}: current smokers are at {current:.4f} against "
                f"{never:.4f} for never-smokers — the smoking gradient is flat"
            )

    @pytest.mark.parametrize(("condition", "age", "sex"), GRADED)
    def test_the_odds_of_a_matched_pair_reproduce_the_cited_ratio(
        self, condition: str, age: int, sex: str
    ) -> None:
        """Finding 1. An odds ratio has to come back out as an odds ratio.

        The original code multiplied a *probability* by a published OR, which does not
        preserve it and overstates the effect exactly where the baseline is large.
        Hypertension is the case that shows it: 0.525 in the fifties times the 2.20
        body-mass figure is 1.155, an impossible probability the clamp then turned
        into 0.995 — a gradient the table never claimed.

        Matched profile, matched everything but body mass, so the only thing between
        the two numbers is the ratio under test. Asserted on the odds scale because
        that is the scale the ratio was published on.
        """
        gradient = RISK_MULTIPLIERS[condition]
        reference = _profile_rate(condition, age, sex, "normal_or_under", "never", "resilient")
        assert _P_FLOOR < reference < _P_CEILING, "the reference cell is clamped"
        for band in BMI_BANDS:
            graded = _profile_rate(condition, age, sex, band, "never", "resilient")
            if not _P_FLOOR < graded < _P_CEILING:
                continue  # a clamped cell cannot testify about a ratio
            realised = (graded / (1 - graded)) / (reference / (1 - reference))
            assert realised == pytest.approx(gradient.bmi[band].value, rel=1e-9), (
                f"{condition}/{band}: the realised odds ratio is {realised:.4f} "
                f"against the cited {gradient.bmi[band].value} — the gradient is not "
                "being applied on the odds scale"
            )

    def test_every_baseline_in_the_whole_domain_is_a_probability(self) -> None:
        """Round 3, finding 1 — exhaustive rather than representative.

        The odds transform's derivation assumes it receives a probability. It used to
        receive ``scale * affinity``, a product of two unbounded positives, and review's
        sweep found **907** cells where that product exceeded 1. Past 1 the transform
        has nothing left to preserve: every band saturates at the ceiling and the
        published gradient disappears — worst in the profiles where the condition is
        most likely, which is exactly where a reader would go looking for it.

        Sampling a few cells would not have found it and did not. This walks the whole
        supported domain, so the claim is "no cell" rather than "no cell we tried".
        """
        offenders: list[str] = []
        for condition in CONDITION_CATALOG:
            for age in range(MIN_APPLICANT_AGE, MAX_APPLICANT_AGE + 1):
                for sex in SEXES:
                    citation = age_band_rate(condition, age, sex)
                    if citation is None:
                        continue
                    intercept = calibrate(condition, age, citation.value)
                    for archetype in HEALTH_ARCHETYPES.values():
                        baseline = _baseline(
                            intercept, archetype.affinity_for(condition)
                        )
                        if not 0.0 < baseline < 1.0:
                            offenders.append(
                                f"{condition}/{age}/{sex}/{archetype.name}={baseline}"
                            )
        assert not offenders, (
            f"{len(offenders)} pre-gradient baselines are not probabilities, e.g. "
            f"{offenders[:5]} — the odds transform is being handed something it "
            "cannot act on"
        )

    def test_the_steepest_profile_still_realizes_its_published_gradient(self) -> None:
        """The witness review named, with no cell allowed to be skipped.

        The earlier gradient check read the ``resilient`` archetype and skipped clamped
        cells, which is precisely how a defect that only bites the *high-prevalence*
        profiles went unseen: at age 55 the multimorbid lumbar baseline was 1.231, all
        four BMI bands pinned to the ceiling, and the 1.79 odds ratio was gone. Skipping
        clamped cells meant skipping the evidence.

        So this asserts twice: no cell here is clamped at all, and the odds ratio
        between the reference band and each other band is the published one.
        """
        condition, age, sex, archetype = "lumbar_disc_degeneration", 55, "male", "multimorbid"
        gradient = RISK_MULTIPLIERS[condition]
        rates = {
            band: _profile_rate(condition, age, sex, band, "never", archetype)
            for band in BMI_BANDS
        }
        for band, probability in rates.items():
            assert _P_FLOOR < probability < _P_CEILING, (
                f"{condition}/{band} is clamped at {probability} in the {archetype} "
                "profile — a saturated cell cannot express a gradient, and this is the "
                "profile where the condition is most likely"
            )

        reference = rates["normal_or_under"]
        for band, probability in rates.items():
            realised = (probability / (1 - probability)) / (reference / (1 - reference))
            assert realised == pytest.approx(gradient.bmi[band].value, rel=1e-9), (
                f"{condition}/{band} in the {archetype} profile realises an odds ratio "
                f"of {realised:.4f} against the cited {gradient.bmi[band].value}"
            )

    def test_a_probability_multiplier_would_have_failed_that(self) -> None:
        """The control: the two scales genuinely differ where it matters.

        Without this the test above could be passing on arithmetic that happens to
        agree — it does agree, to three decimals, whenever the baseline is small. The
        whole finding is that these conditions are not small.
        """
        probability, ratio = 0.525, 2.20
        on_odds = ratio * probability / (1 - probability + ratio * probability)
        assert on_odds == pytest.approx(0.7088, abs=5e-4)
        assert ratio * probability > 1.0, (
            "the multiplicative reading no longer overflows at the hypertension "
            "baseline, so this control has stopped demonstrating the defect"
        )

    def test_every_band_carries_its_own_provenance(self) -> None:
        """Finding 1, second half. "Measured" was covering values nobody measured.

        The knee curve is the case: 2.18 and 2.63 are pooled from twenty-two studies
        and 3.20 is a reading off a dose-response line. One gradient-level tag made
        the third look like the first two, so tags are per band now — and the two
        readings are named as what they are.
        """
        for condition, gradient in RISK_MULTIPLIERS.items():
            for band, ratio in gradient.bmi.items():
                assert ratio.tag in TAG_VALUES, f"{condition}/{band}: {ratio.tag}"
                if ratio.tag in {"interpolated", "extrapolated"}:
                    assert ratio.note.strip(), (
                        f"{condition}/{band} is {ratio.tag} and says nothing about "
                        "how — a derived value with no derivation is the thing these "
                        "tags exist to prevent"
                    )
            for status, ratio in gradient.smoking.items():
                assert ratio.tag in TAG_VALUES, f"{condition}/{status}: {ratio.tag}"

        assert RISK_MULTIPLIERS["knee_cartilage_defect"].bmi["severely_obese"].tag == (
            "interpolated"
        ), "the knee severe-obesity band is a reading inside the published range"
        assert RISK_MULTIPLIERS["lumbar_disc_degeneration"].bmi["severely_obese"].tag == (
            "extrapolated"
        ), "the lumbar severe-obesity band is held flat past the last measured point"

    #: Every condition whose gradient is flat in both axes, and nothing else.
    #:
    #: Written out because the *set* is the claim. An earlier version iterated a
    #: hard-coded list and asserted each member was flat, which is satisfied by a list
    #: that has fallen behind the table — and it had: the docs said "three of nine"
    #: while the catalog held ten conditions and four flat gradients, ``rotator_cuff_tear``
    #: having been flat all along without being listed. Comparing the computed set
    #: against this one fails in both directions.
    FLAT_GRADIENTS = frozenset(
        {
            "cervical_disc_bulge",
            "lumbar_facet_arthropathy",
            "hip_labral_tear",
            "rotator_cuff_tear",
        }
    )

    def test_a_flat_gradient_is_flat_because_its_source_is_silent(self) -> None:
        """The flat set, compared whole, because a subset check cannot go stale safely.

        Flatness is the honest answer where a source reports no gradient, so it is
        asserted rather than left implicit: adding a ratio to one of these has to be a
        deliberate edit with a source behind it, and *removing* one from the set has to
        be noticed too.
        """
        computed = {
            condition
            for condition, gradient in RISK_MULTIPLIERS.items()
            if {r.value for r in gradient.bmi.values()} == {1.0}
            and {r.value for r in gradient.smoking.values()} == {1.0}
        }
        assert computed == self.FLAT_GRADIENTS, (
            f"the flat-gradient set is {sorted(computed)}, not "
            f"{sorted(self.FLAT_GRADIENTS)} — a gradient appeared or disappeared and "
            "the documented set did not move with it"
        )
        assert len(RISK_MULTIPLIERS) == len(CONDITION_CATALOG) == 10, (
            "the catalog changed size; the counts quoted in the module and package "
            "docs are now wrong and this test is the reason they cannot stay wrong"
        )
        for condition in self.FLAT_GRADIENTS:
            assert "Deliberately flat" in RISK_MULTIPLIERS[condition].rationale, (
                f"{condition} is flat but does not say why — flatness with no stated "
                "reason is indistinguishable from an unfilled table row"
            )

    def test_the_gradient_does_not_move_the_population_aggregate(self) -> None:
        """The tension, stated as one assertion.

        A gradient that shifted the aggregate would be trading a calibrated marginal
        for a realistic-looking spread, which is the wrong trade: the marginals are the
        thing this sampler exists to reproduce.
        """
        for condition, age, sex in self.GRADED:
            citation = age_band_rate(condition, age, sex)
            assert citation is not None
            assert _population_rate(condition, age, sex) == pytest.approx(
                citation.value, abs=1e-9
            )

    def test_every_catalog_condition_has_a_documented_gradient_entry(self) -> None:
        """A condition with no entry would raise at draw time, not read as flat."""
        assert set(RISK_MULTIPLIERS) == set(CONDITION_CATALOG)
        for condition, gradient in RISK_MULTIPLIERS.items():
            assert set(gradient.bmi) == set(BMI_BANDS), condition
            assert set(gradient.smoking) == set(SMOKING_STATUSES), condition
            assert gradient.rationale.strip() and gradient.source.strip(), condition

    def test_the_drawn_bmi_cohort_reproduces_the_closed_form_distribution(self) -> None:
        """Two expressions of one distribution, checked against each other.

        ``bmi_distribution`` is what the calibration integrates over and
        ``_draw_bmi_band`` is what the sampler actually draws. If they disagreed, the
        aggregate would be pinned against a population that does not exist.

        **16 and 18 are here because that is where they did disagree.** CDC's obesity
        series starts at 20 and the schema admits applicants from 16; the closed form
        names that gap and reuses the youngest reported band, while the draw turned the
        same missing citation into an obese share of zero and drew nobody obese at all.
        The ages the old test checked — 25, 45, 70 — are all inside the series, so the
        two expressions agreed everywhere the test looked. They are now one expression,
        and these two ages are what would catch a second one appearing.
        """
        for age in (16, 18, 25, 45, 70):
            cohort = _sample(3000, base=11_000_000 + age, applicant={"age": age})
            realised = Counter(h.demographics.bmi_band for h in cohort)
            expected = bmi_distribution(cohort[0].demographics.age)
            for band, share in expected.items():
                assert realised[band] / 3000 == pytest.approx(share, abs=0.03), (
                    f"age {age}, {band}: drew {realised[band] / 3000:.3f} against a "
                    f"closed form of {share:.3f}"
                )

    def test_the_classifier_is_bit_identical_to_the_one_it_replaced(self) -> None:
        """Round 4, finding 1. "Identical" was claimed and was one ULP short of true.

        Centralising the BMI draw the obvious way — walk a cumulative sum of the
        shares — is not the same function as the chain of comparisons it replaced.
        ``severe + (obese - severe)`` reassociates the arithmetic, and for the 40-59
        band that gives ``0.46399999999999997`` where the original compared against the
        source literal ``0.464``. A draw of exactly the representable ``0.464`` lands in
        ``obese`` under one and ``overweight`` under the other.

        One draw in 2^53, on a layer that renders nothing. Worth a test anyway, because
        the *claim* was "every 20+ draw maps identically" and a claim that is nearly
        true is the kind that gets relied on. So the legacy classifier is written out
        here and compared at every cutoff, at the exact representable value, and at the
        float either side of it — for every band the source reports.
        """

        def legacy(draw: float, age: int) -> str:
            citation = OBESITY_PREVALENCE.rate(age, "female")
            obese_share = citation.value if citation is not None else 0.0
            if draw < obese_share * SEVERE_SHARE_OF_OBESE.value:
                return "severely_obese"
            if draw < obese_share:
                return "obese"
            remainder = draw - obese_share
            if remainder < (1.0 - obese_share) * OVERWEIGHT_SHARE_OF_NON_OBESE.value:
                return "overweight"
            return "normal_or_under"

        ages = sorted(
            {
                age
                for age in range(20, MAX_APPLICANT_AGE + 1)
                if OBESITY_PREVALENCE.rate(age, "female") is not None
            }
        )
        assert len(ages) >= 20, "the obesity series has shrunk; this sweep is now thin"

        for age in ages:
            severe, obese, overweight = bmi_band_cutoffs(age)
            probes: list[float] = []
            for cutoff in (severe, obese, obese + overweight):
                probes.extend(
                    (
                        cutoff,
                        math.nextafter(cutoff, 0.0),
                        math.nextafter(cutoff, 1.0),
                    )
                )
            probes.extend((0.0, 0.5, math.nextafter(1.0, 0.0)))
            for draw in probes:
                assert bmi_band_for_draw(draw, age) == legacy(draw, age), (
                    f"age {age}, draw {draw!r}: the classifier gives "
                    f"{bmi_band_for_draw(draw, age)} where the one it replaced gives "
                    f"{legacy(draw, age)}"
                )

    def test_the_distribution_is_derived_from_the_classifiers_own_cutoffs(self) -> None:
        """The other half of "one definition": the shares are not recomputed.

        If :func:`bmi_distribution` derived its shares independently, the two could
        agree in exact arithmetic and disagree at a representable boundary — which is
        the defect above, one layer up. Deriving them *from* the cutoffs makes that
        unrepresentable rather than merely unlikely.
        """
        for age in (18, 25, 45, 70):
            severe, obese, overweight = bmi_band_cutoffs(age)
            shares = bmi_distribution(age)
            assert shares["severely_obese"] == severe
            assert shares["obese"] == obese - severe
            assert shares["overweight"] == overweight
            assert shares["normal_or_under"] == 1.0 - obese - overweight
            assert sum(shares.values()) == pytest.approx(1.0, abs=1e-12)

    def test_ages_below_the_cdc_series_reuse_its_youngest_band(self) -> None:
        """An extrapolation, named rather than buried — every applicant has a body."""
        assert bmi_distribution(17) == bmi_distribution(25)

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

        # And the floor has to be a *clamp*, not a coincidence.
        #
        # m17-4 survived a second time, on the round-2 table, and the reason is worth
        # recording: compressing the archetype affinities to close the anti-fingerprint
        # gap also lifted every cell above the floor on its own, so deleting the clamp
        # changed nothing the loop above could see. The guard had gone vacuous by way
        # of a fix somewhere else — which is the failure mode a corpus-shaped assertion
        # is always one refactor away from. So the clamp is asked directly, at a
        # product no plausible catalog rate reaches.
        starved = _clamped(1e-18)
        assert starved == _P_FLOOR, (
            f"a vanishing probability came back as {starved} rather than "
            f"the floor {_P_FLOOR}; nothing is clamping, and the loop above is only "
            "passing because the current affinities happen to sit above the floor"
        )
        assert _clamped(1.0 - 1e-18) == _P_CEILING, "nothing is clamping at the ceiling"

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

    @pytest.mark.parametrize("age", [16, 18, 25, 45, 68])
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
        # Four at 16-18, where most catalog rows have no source at that age at all;
        # five once the applicant is old enough for the degenerative tables to report.
        # Stated as a floor per age rather than one number, because "the cohort shrank"
        # and "nobody measured this in teenagers" are different facts and only the
        # first is a defect.
        floor = 4 if realised_age < 20 else 5
        assert checked >= floor, (
            f"only {checked} conditions were checkable at age {realised_age}; the "
            "cohort shrank"
        )

    def test_the_under_twenty_population_is_the_one_the_calibration_integrates(self) -> None:
        """Round 3, finding 3 — the witness, written from review's own numbers.

        Two definitions of one distribution drifted at the only place neither was
        exercised. The closed form reuses CDC's youngest reported band for ages 16-19
        and names that as an extrapolation; the draw turned the same missing citation
        into an obese share of **zero**. So the calibration solved an intercept against
        a 35.5%-obese population that the sampler never produced, and an 18-year-old
        male's hypertension came out at 0.239 against a cited 0.300 — a fifth of the
        rate missing, in a cohort nobody was sampling.

        **This has to be sampled, and the first version of it was not.** The analytic
        path always agreed with itself: ``_population_rate`` integrates over
        ``bmi_distribution``, and asserting that it hits its own target is a tautology
        the old code passed too. The defect lived strictly between the *draw* and the
        closed form, so only a drawn cohort can witness it. The mutation gate caught
        that — m17-24 restored the old draw and the analytic assertion sailed through.

        18 and 19 rather than 16 and 17: the hypertension series itself starts at 18,
        and a cell with no citation has nothing to be wrong about. The BMI gap runs
        16-19 and the *distribution* half of it is covered by
        ``test_the_drawn_bmi_cohort_reproduces_the_closed_form_distribution``, which
        does check 16.
        """
        for age in (19, 20):
            count = 4000
            cohort = _sample(
                count,
                base=11_500_000 + age * 1000,
                applicant={"age": age, "sex": "male"},
            )
            # The stated age is a birthday, and a birthday a whole number of years
            # back from the anchor can land the applicant a day short of it. Read the
            # age the ledger actually derived rather than the one asked for, exactly
            # as the parametrized marginal check does.
            realised_age = cohort[0].demographics.age
            citation = age_band_rate("hypertension", realised_age, "male")
            assert citation is not None, f"no hypertension citation at {realised_age}"
            integrated = _population_rate("hypertension", realised_age, "male")
            assert integrated == pytest.approx(citation.value, abs=1e-9)
            drawn = sum(
                1
                for history in cohort
                if any(c.key == "hypertension" for c in history.conditions)
            ) / count
            tolerance = _binomial_tolerance(citation.value, count)
            assert drawn == pytest.approx(citation.value, abs=tolerance), (
                f"age {realised_age} male hypertension is drawn at {drawn:.4f} vs cited "
                f"{citation.value:.4f} (integrated {integrated:.4f}) — the population "
                "the sampler draws from is not the one the calibration solves over"
            )

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
#: The bound is set above the measurement rather than at it because the quantity under
#: control is "no set is a certainty", not "no set is informative": a fingerprint is a
#: deterministic identifier, and evidence is not. A corpus where
#: ``{diabetes, hypertension}`` did **not** point at metabolic burden would be the
#: unrealistic one.
#:
#: **It is measured per claim shape, and the first version was not.** Pooling the seven
#: shapes into one cohort put the worst at 0.934 and looked comfortable; conditioning on
#: the claim's own body parts — which any observer reads straight off the caption — put
#: it at 0.989, on ``{cervical_disc_bulge}`` alone from a cervical-plus-wrist claim.
#: Pooling had been averaging a decisive shape against six that could not produce the
#: same set. The archetype affinities were compressed in response (see
#: ``HEALTH_ARCHETYPES``); the current per-shape worst is 0.828.
MAX_ARCHETYPE_POSTERIOR = 0.97

#: Occurrences a condition set needs before its archetype spread means anything.
#:
#: One observation of a set cannot testify to uniqueness, and a *small* number is worse
#: than useless here because it manufactures the very thing being measured. At the old
#: threshold of twenty, a set whose true worst posterior is 0.83 lands unanimous by pure
#: binomial luck once every ~40 sets (0.83^20 = 0.024), and roughly a hundred and fifty
#: sets clear support across the seven shapes. The probe would have been reporting
#: sampling noise as a fingerprint — or, worse, reporting one and being tuned away.
#:
#: Sixty makes that vanishingly unlikely (0.83^60 = 1.6e-5) while still covering ~88% of
#: every shape. The measured worst falls from 0.913 to 0.825 purely by removing the
#: noise, which is the tell that twenty was measuring the wrong thing.
MIN_SET_SUPPORT = 60

#: The provenance grades a gradient band may carry.
#:
#: Mirrored from the ``Tag`` alias rather than imported, because a test that read the
#: alias would accept whatever the alias grew. The point of asserting it here is that
#: adding a grade is a decision somebody has to make twice.
TAG_VALUES: frozenset[str] = frozenset(
    {
        "measured",
        "interpolated",
        "extrapolated",
        "counsel_confirmed",
        "counsel_unconfirmed",
        "invented",
    }
)

#: Applicants drawn per claim shape for the anti-fingerprint probes.
#:
#: Seven shapes at this size is 42k derivations, which is the runtime price of measuring
#: the property on the object an observer actually sees, at a support threshold high
#: enough to mean something. The cohorts are cached across the three probes below, so
#: that is 42k in total and not 126k. Smaller cohorts push the common sets under
#: ``MIN_SET_SUPPORT`` and the probes go vacuous rather than red, which is why the
#: support and coverage floors are asserted before the property is.
SHAPE_COHORT_N = 6000

#: Share of a shape's applicants the supported sets must account for.
#:
#: Measured floor is 0.844, on ``lumbar_spine+shoulder`` — the richest shape, whose
#: longer tail of distinct sets is exactly why it is the binding one. It was 0.880
#: before the calibration moved to a logistic link: bounding every baseline inside
#: (0, 1) redistributed a little mass into rarer condition counts, which lengthens
#: exactly this tail. A distribution-shaped number moving when the distribution
#: changes is not a regression. Set below the
#: measurement because this is an anti-vacuity check, not a property: it exists so a
#: probe that has quietly retreated into the tail fails instead of passing.
MIN_SHAPE_COVERAGE = 0.80


@cache
def _shape_posteriors(
    parts: tuple[str, ...], base: int
) -> dict[frozenset[str], Counter[str]]:
    """Archetype spread per condition set, for one claim shape.

    Cached because three probes read the same cohorts and the derivation is pure. The
    returned mapping is treated as read-only by every caller.
    """
    by_set: dict[frozenset[str], Counter[str]] = defaultdict(Counter)
    for history in _sample(SHAPE_COHORT_N, base=base, parts=parts):
        by_set[history.condition_keys()][history.archetype] += 1
    return by_set


class TestProfileMembershipIsNotAFingerprint:
    """Gate 3. Within-profile variation is mandatory, so it has to be falsifiable.

    **What M1 guarantees, stated exactly.** Two rounds of review pushed on this and
    the second one pushed it into a shape worth writing down, because the earlier
    wording promised more than any sampler can deliver:

    a. **Singleton-freedom, within every demographic cell and claim shape.** No
       condition set is producible by only one archetype. This is exact rather than
       empirical — it follows from every per-archetype probability sitting strictly
       inside ``(0, 1)``, so every subset has positive probability under every
       archetype — and it is what "no observation rules a profile out" actually means.
    b. **A 0.97 posterior bound on shape-conditioned common sets**, measured as below:
       per claim shape, over sets with real support, pooled across demographics.

    **What M1 does not guarantee, with the counterexample.** The bound in (b) is not
    conditioned on demographics, and review found a cell where it does not hold: a
    62-year-old severely obese female never-smoker on a lumbar-plus-shoulder claim,
    where the *empty* condition set already gives ``resilient`` a posterior of 0.9801.
    That is not a defect to tune away, and deliberately so. The archetype prior really
    does concentrate with age and body mass — that is the epidemiology the steer
    exists to carry — and flattening it to win a number here would make the corpus
    less realistic in exchange for a guarantee nobody consumes, because **the archetype
    label is published nowhere**. It is a latent variable of the sampler, not a fact
    about a case.

    **Where the real question is answered.** The claim that matters is
    ``P(archetype | every analyzer-visible feature)`` — rendered documents, document
    counts, section lengths, manifest fields — and none of those exist in M1. That is
    M4's leakage anti-probe, specified in **AJC-63**, and it is the one that can fail
    for a reason a consumer would feel. Note F's standing warning points the same way:
    the leak to fear is a correlation between profile and something the *renderer*
    varies.

    Two claims below, and they are genuinely different strengths.

    The **structural** one — every archetype can produce every condition — is exact
    and is asserted analytically in ``TestTheCalibrationSolves``. No chain of observed
    conditions can rule an archetype out, because no probability is ever zero.

    The **empirical** one below is weaker on purpose, because the strong version is
    false for any sampler and would be wrong to want. Conditions really are evidence
    about a health profile: someone carrying diabetes and hypertension really is more
    likely to be metabolically burdened, and a corpus that hid that would be less
    realistic, not more. What must not exist is a set that *settles* the question.

    **Cohort shape is load-bearing, twice over.** These run over the one-and-two-region
    claims a caseload actually contains. An artificial case naming all five gated
    regions makes almost every applicant comorbid, so the sparse tail — nobody with
    anything — comes back attributable to ``resilient`` alone. That is an artifact of a
    case shape the corpus does not contain, and measuring the property on it would fail
    the sampler for a claim nobody makes.

    And the shapes are measured **separately**, never pooled. The body parts on a claim
    are visible on the face of the file: an observer trying to recover the health
    profile already knows the caption, so the posterior that matters is
    ``P(archetype | conditions, body parts)``. Averaging over shapes answers a question
    nobody is in a position to ask, and it hid a 0.989 posterior behind a 0.934 one for
    a full review round. ``test_pooling_claim_shapes_would_have_hidden_the_leak`` keeps
    that difference asserted rather than remembered.

    **What M4 adds.** The leakage anti-probe there makes the claim this one cannot:
    that a classifier trained on the *analyzer-visible artifacts* — rendered documents,
    manifests, document counts — cannot recover the archetype better than chance. That
    probe needs artifacts, and in M1 there are deliberately none, because nothing about
    this ledger reaches any output at all. It also covers the leak this test structurally
    cannot see: a correlation between profile and something the renderer varies, such as
    document count or section length, which is note F's standing warning.
    """

    @pytest.mark.parametrize(
        ("index", "parts"), list(enumerate(REALISTIC_PART_SETS)), ids=lambda v: str(v)
    )
    def test_no_well_supported_condition_set_belongs_to_one_archetype(
        self, index: int, parts: tuple[str, ...]
    ) -> None:
        by_set = _shape_posteriors(parts, 8_000_000 + index * 10_000)
        supported = {
            key: spread
            for key, spread in by_set.items()
            if sum(spread.values()) >= MIN_SET_SUPPORT
        }
        assert len(supported) >= 5, (
            f"{parts}: only {len(supported)} sets reached support {MIN_SET_SUPPORT}; "
            "the cohort is too small for this assertion to mean anything"
        )
        covered = sum(sum(s.values()) for s in supported.values()) / SHAPE_COHORT_N
        assert covered > MIN_SHAPE_COVERAGE, (
            f"{parts}: supported sets cover only {covered:.1%} of the shape, so the "
            "probe is reading the tail rather than the corpus"
        )

        singleton = {
            tuple(sorted(key)): dict(spread)
            for key, spread in supported.items()
            if len(spread) == 1
        }
        assert not singleton, (
            f"{parts}: condition sets produced by exactly one archetype despite "
            f"appearing {MIN_SET_SUPPORT}+ times: {dict(list(singleton.items())[:5])} "
            "— profile membership is recoverable outright from the conditions"
        )

    @pytest.mark.parametrize(
        ("index", "parts"), list(enumerate(REALISTIC_PART_SETS)), ids=lambda v: str(v)
    )
    def test_no_condition_set_makes_an_archetype_a_near_certainty(
        self, index: int, parts: tuple[str, ...]
    ) -> None:
        """The quantitative half: informative is fine, decisive is not."""
        by_set = _shape_posteriors(parts, 8_000_000 + index * 10_000)
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
            f"{parts}: {worst_key} identifies its archetype with posterior "
            f"{worst:.3f}; a condition set that settles the profile is a fingerprint"
        )

    #: The demographic corners the singleton check walks, plus review's witness cell.
    #:
    #: Corners rather than a grid: the steer is monotone in each input, so the extremes
    #: are where a probability would reach a bound if it ever did. The witness cell is
    #: carried explicitly because it is the one review found, and a check that no
    #: longer covers it would have quietly stopped answering the finding.
    DEMOGRAPHIC_CELLS: tuple[tuple[int, str, str, str], ...] = (
        (25, "female", "normal_or_under", "never"),
        (25, "male", "severely_obese", "current"),
        (45, "female", "obese", "former"),
        (62, "female", "severely_obese", "never"),  # review's witness cell
        (70, "male", "normal_or_under", "current"),
        (70, "female", "severely_obese", "current"),
    )

    @pytest.mark.parametrize(("age", "sex", "bmi", "smoking"), DEMOGRAPHIC_CELLS)
    def test_no_condition_set_is_producible_by_only_one_archetype(
        self, age: int, sex: str, bmi: str, smoking: str
    ) -> None:
        """Guarantee (a), proved rather than sampled — round 2, finding 2.

        Conditions are drawn independently given the archetype, so the probability of
        any particular *set* under an archetype is a product of per-condition terms and
        their complements. That product is zero only if some term is zero. Assert every
        term is strictly inside ``(0, 1)`` for every archetype in this cell, and
        singleton-freedom follows for all 2^n sets at once — including the sets a
        cohort of any size would never happen to draw.

        A sampled version of this claim would be strictly weaker and vastly slower: it
        could only ever speak about the sets it saw.
        """
        for shape in REALISTIC_PART_SETS:
            eligible = eligible_conditions(frozenset(shape))
            assert eligible, f"{shape} makes nothing eligible"
            for condition in eligible:
                probabilities = condition_probabilities(condition, age, sex, bmi, smoking)
                if not probabilities:
                    continue  # a NOT-FOUND cell: nobody measured it, so nothing is drawn
                assert {name for name, _ in probabilities} == set(HEALTH_ARCHETYPES)
                for name, probability in probabilities:
                    assert 0.0 < probability < 1.0, (
                        f"{shape}/{condition}/{name} is {probability} at "
                        f"age {age} {sex} {bmi} {smoking} — an archetype that cannot "
                        "produce this condition, or cannot avoid it, makes some "
                        "condition set unique to the others"
                    )

    def test_the_link_saturates_and_the_clamp_is_what_catches_it(self) -> None:
        """Which mechanism actually holds the guarantee, measured rather than assumed.

        The logistic link keeps a baseline inside ``(0, 1)`` for finite log-odds *in
        exact arithmetic*. In float64 it does not: ``sigmoid(38)`` is already exactly
        1.0, and the intercept search brackets ±40. So the open interval at the
        extremes is held by the **clamp**, not by the link, and the two are not
        redundant the way they look.

        This is asserted because the mutation gate said so. m17-22 widened the clamp to
        the closed interval and survived every mid-range cell — the link covers those —
        and only the search bounds distinguish the two mechanisms. A guard that cannot
        tell which of two safeguards is load-bearing will happily watch one be removed.
        """
        assert _logistic(38.0) == 1.0, (
            "the link no longer saturates at 38, so this test has stopped "
            "demonstrating that the clamp is what holds the bound at the extremes"
        )
        assert _INTERCEPT_BOUND >= 38.0, (
            "the intercept search no longer reaches the saturating region, so the "
            "clamp is no longer reachable from a solve and this test is measuring "
            "something the engine cannot produce"
        )
        for intercept in (_INTERCEPT_BOUND, -_INTERCEPT_BOUND):
            for affinity in (0.85, 2.0):
                probability = _graded(
                    intercept, affinity, "hypertension", "obese", "current"
                )
                assert 0.0 < probability < 1.0, (
                    f"intercept {intercept} affinity {affinity} produced "
                    f"{probability} — an archetype that reaches certainty can be "
                    "ruled in or out by one observation"
                )

    def test_the_singleton_proof_rests_on_something_that_can_fail(self) -> None:
        """The control for the argument above, not for the code.

        The proof is only as good as its premise, so the premise is exercised: a
        probability of exactly zero or one really does make a set unique to one
        archetype. Written out arithmetically because the point is the reasoning, and
        the reasoning is what a reader has to check.
        """
        live = {"a": 0.4, "b": 0.001}
        dead = {"a": 0.4, "b": 0.0}

        def probability_of_exactly_b(cell: dict[str, float]) -> float:
            return (1 - cell["a"]) * cell["b"]

        assert probability_of_exactly_b(live) > 0.0
        assert probability_of_exactly_b(dead) == 0.0, (
            "a zero-probability condition would leave the set {b} unreachable for this "
            "archetype, which is exactly the exclusion the floor prevents"
        )

    def test_pooling_claim_shapes_would_have_hidden_the_leak(self) -> None:
        """The control for the measurement itself, and the reason it is parametrized.

        The first version of these probes pooled all seven claim shapes into one
        cohort, and the pooling *diluted* the posterior: a set that is decisive on a
        cervical-plus-wrist claim is diluted by every lumbar claim that produced the
        same set for a different reason. That is not a defensible average, because
        **body parts are visible on the face of the file** — an observer reads the
        claim shape off the caption and never has to average over shapes at all.

        So the pooled number is computed here alongside the per-shape worst, and the
        two are asserted to differ. If they ever stop differing, the parametrization
        above has stopped buying anything and this comment is wrong.
        """
        pooled: dict[frozenset[str], Counter[str]] = defaultdict(Counter)
        per_shape_worst = 0.0
        for index, parts in enumerate(REALISTIC_PART_SETS):
            by_set = _shape_posteriors(parts, 8_000_000 + index * 10_000)
            for key, spread in by_set.items():
                if sum(spread.values()) >= MIN_SET_SUPPORT:
                    posterior = max(spread.values()) / sum(spread.values())
                    per_shape_worst = max(per_shape_worst, posterior)
                pooled[key].update(spread)

        pooled_worst = max(
            (
                max(spread.values()) / sum(spread.values())
                for spread in pooled.values()
                if sum(spread.values()) >= MIN_SET_SUPPORT
            ),
            default=0.0,
        )
        assert per_shape_worst > pooled_worst, (
            f"per-shape worst {per_shape_worst:.4f} is no higher than the pooled "
            f"{pooled_worst:.4f}; pooling has stopped hiding anything and the "
            "parametrization above is no longer earning its runtime"
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


#: Claims the docs have made and then outlived, each with what replaced it.
#:
#: Round 3 found five superseded statements still being asserted in prose: the old
#: ``clamp(s * r)`` calibration equation, an "archetype is not recoverable" claim
#: broader than anything M1 delivers, counsel's superseded "one in three", a
#: "three of nine" count that was never right about the catalog's ten conditions and
#: four flat gradients, and a comment describing an award default that had already
#: changed to ``None``.
#:
#: Every one of them was true when written. That is what makes them worth a sweep
#: rather than a proofread: prose that was true once fails silently, and the only
#: reliable way to keep it honest is to make the superseded form unrepresentable.
SUPERSEDED_DOC_CLAIMS: tuple[tuple[str, str], ...] = (
    ("clamp(s * r_a)", "the calibration solves a logistic intercept, not a scale"),
    ("sum(w_a * clamp(s * r_a))", "same equation, spelled out"),
    ("one in three", "counsel revised the surfacing union to one in two on 2026-08-10"),
    (
        "membership therefore is not recoverable",
        "M1 guarantees singleton-freedom and a shape-conditioned posterior bound, "
        "not non-recoverability — see TestProfileMembershipIsNotAFingerprint",
    ),
    ("Three of the nine", "the catalog holds ten conditions and four flat gradients"),
    ("three of nine", "same count"),
    (
        'defaults its own\n#: ``resolution_type`` to ``stipulated_award``',
        "PriorAwardEntry.resolution_type now defaults to None, meaning the claim's own",
    ),
    (
        "the award's default value\n        makes it the easy one to write by accident",
        "the award default is None now, so silence cannot disagree with the claim",
    ),
    ("0.50/0.76", "the reference population's E[P(any)] is 0.771, not 0.76"),
    (
        "(25-62 inclusive, uniform)",
        "the cast draws a day offset, not an age; reference_age_weights derives the "
        "trapezoid with half-weight endpoints and an age-24 tail",
    ),
    ("= **66%**", "implied file visibility is 65% at 0.50 / 0.771"),
    (
        "divides by the realised aggregate",
        "the gate divides by the reference population's expected aggregate; dividing "
        "by the realised per-applicant figure is the form that could not attain it",
    ),
    (
        "cannot leave ``(0, 1)``",
        "the link saturates in float64 (sigmoid(38) == 1.0); it is strict over "
        "calibrated production intercepts and the final clamp owns the extremes",
    ),
    (
        "the documentation gate has an honest divisor",
        "the gate divides by expected_any_condition(); P_ANY_CONDITION_MEASURED is a "
        "sampled cross-check of it, not the divisor",
    ),
    (
        "Measured over 21,000 sampled cases",
        "the cross-check draws 1,500 per shape across seven shapes — 10,500 cases, "
        "equally weighted; see AGGREGATE_PROBE_N",
    ),
)

#: How far either side of a hit counts as "the passage it sits in".
#:
#: Roughly a long paragraph. Wide enough that a note recording a revision covers the
#: number it is recording, narrow enough that a ``supersed`` twenty lines away cannot
#: launder an unrelated claim.
DOC_CONTEXT_WINDOW = 400

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
PRODUCTION_PACKAGE = PACKAGE_ROOT / "src" / "wc_caseload_engine"


def production_modules() -> tuple[Path, ...]:
    """Every Python module this package ships, found rather than listed.

    Round 6, finding 2. The sweep used to name three modules by hand, and the
    documentation it was written to police had already moved out of them: the corrected
    non-uniform age law lives in ``case_context._DERIVED_AGE_RANGE``'s docstring, which
    was not on the list, so restating the superseded uniform claim *there* stayed green.

    A hand-written list of files to check has the same failure mode as a hand-written
    list of conditions to check (see ``m17-29``): it is correct on the day it is written
    and silently narrows every time the package grows. Discovery cannot go stale.
    """
    return tuple(sorted(PRODUCTION_PACKAGE.rglob("*.py")))


def superseded_hits(text: str, label: str, window: int = DOC_CONTEXT_WINDOW) -> list[str]:
    """The checker itself, factored out so a control can be run *through* it.

    Case-folded, because a superseded claim restated at the start of a sentence is the
    same claim — the mutation gate found that: ``m17-30`` reinstated the
    non-recoverability line capitalised and a case-sensitive sweep matched nothing.

    A hit is exonerated only by the word ``supersed`` inside its own passage. That
    exemption is what lets provenance survive — ``P_SURFACES_IN_FILE``'s rationale
    quotes counsel's retired "one in three" on purpose — and it is deliberately an
    exemption an author can satisfy honestly and cannot satisfy by accident.
    """
    folded = text.lower()
    offenders: list[str] = []
    for raw_phrase, replacement in SUPERSEDED_DOC_CLAIMS:
        phrase = raw_phrase.lower()
        start = folded.find(phrase)
        while start != -1:
            passage = folded[max(0, start - window) : start + len(phrase) + window]
            if "supersed" not in passage:
                line = folded.count("\n", 0, start) + 1
                offenders.append(f"{label}:{line}: {raw_phrase!r} — {replacement}")
            start = folded.find(phrase, start + 1)
    return offenders


class TestTheDocsDoNotStateSupersededContracts:
    """Round 3, finding 4. Documentation rot, mechanised instead of proofread.

    The package already has two meta-guards that make stale docs *impossible* rather
    than merely discouraged — the "not yet honoured" marker sweep and the message
    registry. This is the third, and it exists because review found five superseded
    claims in one pass, every one of them true on the day it was written.
    """

    def test_the_sweep_reads_every_module_this_package_ships(self) -> None:
        """Round 6, finding 2. Coverage of the sweep, not just its verdict.

        The old list named three modules, and the age-law documentation had already
        moved to a fourth — ``case_context``, where the corrected non-uniform law is
        now written down. Restating the superseded uniform claim there passed. A sweep
        is only as honest as its file list, so the file list is now discovered and this
        assertion is what proves the discovery reached everything.
        """
        scanned = {path.stem for path in production_modules()}

        # Enumerated by the *import* machinery rather than by another glob. Checking a
        # glob against a glob compares a method with itself and agrees about anything
        # they both miss; pkgutil answers "what can be imported from this package",
        # which is the question that matters and is arrived at a different way.
        importable = {
            info.name
            for info in pkgutil.iter_modules([str(PRODUCTION_PACKAGE)])
            if not info.ispkg
        }
        assert importable, "pkgutil found no modules at all; the path is wrong"
        assert not importable - scanned, (
            "the doc sweep does not reach every module this package ships; unswept: "
            f"{sorted(importable - scanned)}"
        )
        assert "case_context" in scanned, (
            "case_context owns the corrected age-law documentation and is unswept — "
            "this is the exact gap round 6 found"
        )

    def test_no_module_still_states_a_superseded_contract(self) -> None:
        """A retired claim may be *quoted*, but only where it is marked as retired.

        The distinction is real and worth encoding rather than hand-waving.
        ``P_SURFACES_IN_FILE``'s rationale says counsel first answered "one in three"
        and later "one in two" — that is provenance, and deleting it would hide that a
        counsel-confirmed number moved by half its own value on re-asking. What the
        sweep forbids is the same phrase used as a live statement of the contract.

        So a hit passes only if its own passage says it has been superseded. That is a
        rule an author can satisfy honestly and cannot satisfy by accident.
        """
        offenders: list[str] = []
        for path in production_modules():
            offenders.extend(
                superseded_hits(
                    path.read_text(encoding="utf-8"),
                    path.relative_to(PACKAGE_ROOT).as_posix(),
                )
            )
        assert not offenders, "superseded claims still stated:\n  " + "\n  ".join(offenders)

    def test_quoting_a_retired_number_needs_the_word_that_retires_it(self) -> None:
        """The control for the exemption, so the exemption cannot swallow the rule."""
        grounding = (PRODUCTION_PACKAGE / "clinical_grounding.py").read_text(
            encoding="utf-8"
        )
        start = grounding.find("one in three")
        assert start != -1, (
            "the historical record of counsel's first answer has been deleted; the "
            "revision it documents is now invisible"
        )
        window = grounding[start - DOC_CONTEXT_WINDOW : start + DOC_CONTEXT_WINDOW]
        assert "supersed" in window.lower(), (
            "the surviving 'one in three' is no longer marked as superseded, so the "
            "sweep above is exempting it on a technicality"
        )

    #: Sentences this package really shipped, kept so the sweep can be tested on them.
    #:
    #: Each is verbatim from a passage that was live in a reviewed commit. A control
    #: written from imagination tests the phrase list against itself; these test it
    #: against the prose it was built to catch.
    PLANTED_STALE_PASSAGES: tuple[str, ...] = (
        "the calibration solves for the one scale s where sum(w_a * clamp(s * r_a))",
        "Ages mirror case_context._DERIVED_AGE_RANGE (25-62 inclusive, uniform), which",
        "Counsel's revision to 0.50 puts it at 0.50/0.76 = **66%**, which no longer",
        "held exactly regardless, because the documentation gate divides by the "
        "realised aggregate.",
        "the award's default value\n        makes it the easy one to write by accident",
        "A logistic link cannot leave ``(0, 1)``, so the property holds",
        "Membership therefore is not recoverable from the conditions alone",
        "Recorded so the documentation gate has an honest divisor and so the number",
        "Measured over 21,000 sampled cases at derived ages across the seven realistic",
    )

    @pytest.mark.parametrize("passage", PLANTED_STALE_PASSAGES)
    def test_the_sweep_would_notice_a_superseded_claim(self, passage: str) -> None:
        """The planted controls. A sweep over phrases nobody writes proves nothing.

        Parametrized rather than pooled so a phrase that stops matching names itself.
        Round 4 found three stale passages the sweep walked straight past — the 66%
        arithmetic, the award-default wording and the over-strong link claim — and a
        single pooled control would have stayed green through all three, because one
        surviving match is enough to satisfy ``any``.

        Round 6, finding 2: the control now goes through :func:`superseded_hits`, the
        function the sweep itself calls, instead of asking whether some phrase is a
        substring of the passage. Membership tests the *list*; this tests the
        **checker** — case folding, the passage window, and the ``supersed`` exemption
        included. A checker that had stopped flagging everything would have passed the
        old control, because the old control never ran it.
        """
        hits = superseded_hits(passage, "planted")
        assert hits, (
            f"the checker does not flag {passage[:60]!r} — a passage this package "
            "actually shipped could be restated without anything going red"
        )

    def test_the_checker_folds_case_and_honours_its_own_exemption(self) -> None:
        """The checker's three moving parts, exercised on one shipped passage.

        Parametrized controls prove the phrase list reaches the prose. This proves the
        *mechanism* does what the sweep's docstring promises: it flags, it folds case,
        and it stands down inside a passage that marks the claim retired. All three
        have been wrong at some point — ``m17-30`` got through a case-sensitive sweep
        by capitalising a sentence — and each is one line here.
        """
        passage = "Membership therefore is not recoverable from the conditions alone"

        assert superseded_hits(passage, "planted"), (
            "the checker no longer flags a passage this package shipped"
        )
        assert superseded_hits(passage.upper(), "planted"), (
            "the checker has become case-sensitive; capitalising a superseded claim "
            "is enough to restate it, which is how m17-30 got through once already"
        )
        assert not superseded_hits(f"{passage} — superseded on 2026-08-08.", "planted"), (
            "the supersed exemption no longer works, so provenance cannot be quoted "
            "and the sweep will be satisfied by deleting history instead of marking it"
        )


def _condition_from_catalog_stub(key: str) -> Any:
    """A minimal undocumented condition, for exercising the gate on its own.

    Built by hand rather than sampled because the gate is what is under test and a
    sampled condition would drag the whole derivation in with it.
    """
    spec = CONDITION_CATALOG[key]
    return MedicalCondition(
        id=f"cond-{key}",
        key=key,
        label=spec.label,
        body_system=spec.body_system,
    )


def _reference_cohort(total: int, base: int) -> list[Any]:
    """A cohort drawn from the *reference population* the unions are defined over.

    Claim shapes in their documented proportions rather than equally, because the
    surfacing union is an expectation over a caseload and a caseload is not an equal
    mix of shapes. Ages arrive from the cast's own DOB draw, which is uniform over
    the law ``reference_age_weights`` derives; sex, body mass and smoking follow their
    tables. So this
    cohort *is* the population :func:`expected_any_condition` integrates over, which is
    what makes the sampled check below a check of the same claim as the analytic one.
    """
    cohort: list[Any] = []
    for index, (shape, knob) in enumerate(sorted(REFERENCE_CLAIM_SHAPES.items())):
        count = round(total * knob.value)
        cohort.extend(_sample(count, base=base + index * 100_000, parts=shape))
    return cohort


#: Applicants drawn for the union check.
#:
#: Sized so four standard errors on the surfacing union (about 0.0119) sits clearly
#: below the 0.016 bias the per-applicant gate produced. A smaller cohort cannot
#: resolve the defect this test exists to catch, which is asserted rather than assumed
#: by ``test_the_sampled_tolerance_is_tighter_than_the_bias_it_missed``.
_UNION_COHORT_N = 28_000


def _binomial_tolerance(probability: float, count: int, sigmas: float = 4.0) -> float:
    """A tolerance derived from sampling error rather than chosen to fit.

    Four standard errors — a two-sided 1-in-16000 event under the null. Wide enough
    that a correct sampler does not flake, narrow enough that a structural miss cannot
    hide inside it. The old ±0.02 was neither: it was the same order as the 0.016 bias
    it was supposed to be watching for, and duly missed it for a round.
    """
    return sigmas * math.sqrt(probability * (1.0 - probability) / count)


class TestTheDocumentationGate:
    """Gate: the two published unions, held in expectation over the reference population.

    "In expectation over a population" is the correction, and it is the whole finding.
    Counsel's rate is a statement about a *caseload*; the first implementation tried to
    hold it inside each applicant by dividing that applicant's own ``P(any)`` into it
    and capping at 1. The cap is one-sided, so every applicant below the target
    contributed less than the target and none contributed more — the aggregate landed
    at 0.484 against 0.50, and the ±0.02 sampled tolerance was too wide to see a 0.016
    bias.

    Both halves are checked now: the analytic identity, exactly, and the sampled
    realisation against a tolerance derived from binomial standard error.
    """

    def test_the_age_weights_are_the_law_the_cast_actually_draws(self) -> None:
        """Round 5, finding 2. The reference population has to be the real one.

        A ``REFERENCE_AGES`` constant declared a uniform band and the cast draws nothing
        of the sort: ``randint(low*365, high*365) + randint(0, 364)`` convolves uniforms
        into a trapezoid, a 365-day year against a calendar with leap days drags a
        little mass onto age 24, and the endpoints carry about half an interior year's
        weight. The error was in the fifth decimal — and the *claim* was an identity at
        1e-12 over "the generation population", which is a different thing from being
        approximately right.

        Enumerated the slow way here against the closed form the module uses, because
        an analytic weight table checked against another analytic weight table would
        only prove they were written by the same hand.
        """
        low, high = DERIVED_AGE_RANGE
        counted: Counter[int] = Counter()
        for coarse in range(low * 365, high * 365 + 1):
            for fine in range(0, 365):
                born = ANCHOR_DATE - timedelta(days=coarse + fine)
                counted[
                    ANCHOR_DATE.year
                    - born.year
                    - ((ANCHOR_DATE.month, ANCHOR_DATE.day) < (born.month, born.day))
                ] += 1
        total = sum(counted.values())
        enumerated = {age: count / total for age, count in sorted(counted.items())}

        assert reference_age_weights() == enumerated, (
            "the closed-form age weights disagree with an exact enumeration of the "
            "date-of-birth law the cast executes"
        )

        assert 24 in enumerated, (
            "the age-24 tail has vanished; a 365-day year against a calendar with leap "
            "days is what produces it, so its absence means the law changed"
        )
        assert enumerated[low] < enumerated[low + 5] / 1.5, (
            "the low endpoint no longer carries reduced weight, so the distribution "
            "has become the uniform one this test exists to refute"
        )
        assert enumerated[high] < enumerated[high - 5] / 1.5, (
            "the high endpoint no longer carries reduced weight"
        )
        assert sum(enumerated.values()) == pytest.approx(1.0, abs=1e-12)

    def test_the_expected_union_is_exactly_the_counsel_confirmed_rate(self) -> None:
        """Analytic, deterministic, and tight — no cohort involved.

        ``E[surfaces] = E[P(any)] * q`` because ``q`` is a constant, so setting
        ``q = target / E[P(any)]`` makes the identity hold to floating point. There is
        no sampling in this assertion at all, which is why it can be asserted at 1e-12
        where the cohort below has to allow four standard errors.
        """
        realised = expected_any_condition() * surfacing_conditional()
        assert realised == pytest.approx(P_SURFACES_IN_FILE.value, abs=1e-12), (
            f"the expected surfacing union is {realised:.6f} against counsel's "
            f"{P_SURFACES_IN_FILE.value} — the gate cannot attain its own target"
        )

        billing = realised * billing_conditional()
        assert billing == pytest.approx(P_BILLING_CODED.value, abs=1e-12), (
            f"the expected billing union is {billing:.6f} against NCCI's "
            f"{P_BILLING_CODED.value}"
        )

    def test_the_per_applicant_form_could_not_have_attained_it(self) -> None:
        """The witness for the finding, kept as arithmetic rather than as a memory.

        ``E[min(P_any, target)] < target`` whenever any applicant sits below the
        target, and the shortfall is exactly what the old gate lost. Asserting the
        inequality *and* the measured magnitude means a future change that quietly
        reintroduces per-applicant capping fails here with a number attached.
        """
        expected = expected_any_condition()
        female = FEMALE_SHARE.value
        smoking = {status: knob.value for status, knob in SMOKING_DISTRIBUTION.items()}
        target = P_SURFACES_IN_FILE.value

        capped = 0.0
        for age, age_weight in reference_age_weights().items():
            bmi_weights = bmi_distribution(age)
            for sex, sex_share in (("female", female), ("male", 1.0 - female)):
                for band, bmi_share in bmi_weights.items():
                    for status, smoking_share in smoking.items():
                        for shape, knob in REFERENCE_CLAIM_SHAPES.items():
                            p_any = probability_of_any_condition(
                                age, sex, band, status, frozenset(shape)
                            )
                            weight = (
                                age_weight * sex_share * bmi_share * smoking_share
                                * knob.value
                            )
                            capped += weight * min(p_any, target)

        assert capped < target - 0.005, (
            f"the per-applicant form now reaches {capped:.4f} against a target of "
            f"{target} — either every applicant is above the target (in which case "
            "this witness is obsolete) or the capping has been removed twice"
        )
        assert expected > target, (
            "the reference population's P(any) has fallen below the surfacing target, "
            "which would make the global conditional exceed 1 and cap all over again"
        )

    def test_the_gate_conditional_ignores_the_applicants_own_risk(self) -> None:
        """The mutation guard for the fix, and it has to be deterministic.

        The analytic identity above never calls the gate, and the sampled check below
        cannot resolve a 0.016 bias at four standard errors — which is the same fact
        that let the defect through in the first place. So the property is asserted
        directly instead: with the rng held identical, the gate's decision must not
        depend on ``p_any``. Under the per-applicant form it depends on nothing else.
        """
        conditions = [
            _condition_from_catalog_stub("hypertension"),
            _condition_from_catalog_stub("diabetes"),
        ]
        low = _apply_documentation_gate(list(conditions), 0.30, random.Random(11))
        high = _apply_documentation_gate(list(conditions), 0.95, random.Random(11))

        assert [c.surfaces_in_file for c in low] == [c.surfaces_in_file for c in high], (
            "the surfacing decision moved when only the applicant's own P(any) "
            "changed — the conditional is per-applicant again, and a per-applicant "
            "conditional cannot attain a caseload-level union"
        )
        assert [c.billing_coded for c in low] == [c.billing_coded for c in high]

    def test_the_sampled_tolerance_is_tighter_than_the_bias_it_missed(self) -> None:
        """The instrument, checked against the defect it failed to catch.

        A tolerance can only be wrong in one direction here, and a passing test cannot
        notice: widening it never reddens anything, which is why the mutation gate
        scored a hard-coded ±0.02 as SURVIVED. So the width itself is asserted, against
        the number it has to be able to resolve — the per-applicant gate's 0.016
        shortfall. ±0.02 fails this and four standard errors at this cohort size does
        not, which is the whole distinction.
        """
        missed_bias = P_SURFACES_IN_FILE.value - 0.484
        tolerance = _binomial_tolerance(P_SURFACES_IN_FILE.value, _UNION_COHORT_N)
        assert tolerance < missed_bias, (
            f"the sampled tolerance is {tolerance:.4f} against a structural bias of "
            f"{missed_bias:.4f} that this test exists to catch — it cannot resolve the "
            "defect it is guarding, which is exactly the state it was found in"
        )

    def test_the_realised_unions_match_in_a_drawn_cohort(self) -> None:
        """The sampled half, at a tolerance derived rather than chosen."""
        cohort = _reference_cohort(_UNION_COHORT_N, base=9_000_000)
        total = len(cohort)
        surfaced = sum(1 for h in cohort if any(c.surfaces_in_file for c in h.conditions))
        billed = sum(1 for h in cohort if any(c.billing_coded for c in h.conditions))

        surfacing_tolerance = _binomial_tolerance(P_SURFACES_IN_FILE.value, total)
        assert surfaced / total == pytest.approx(
            P_SURFACES_IN_FILE.value, abs=surfacing_tolerance
        ), (
            f"{surfaced / total:.4f} of applicants surface a comorbidity against "
            f"counsel's {P_SURFACES_IN_FILE.value}, outside {surfacing_tolerance:.4f} "
            f"({total} applicants)"
        )

        billing_tolerance = _binomial_tolerance(P_BILLING_CODED.value, total)
        assert billed / total == pytest.approx(
            P_BILLING_CODED.value, abs=billing_tolerance
        ), (
            f"{billed / total:.4f} carry one in billing against NCCI's "
            f"{P_BILLING_CODED.value}, outside {billing_tolerance:.4f}"
        )

    def test_billing_coded_never_escapes_the_surfacing_union(self) -> None:
        """The measured 6.6% is a floor *inside* the union, not a competing figure."""
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

        Note C's per-condition marginals force an aggregate near 0.76, not the 0.55
        the design record expected. SME ruling 5 made the aggregate a *derived check*
        rather than an asserted knob, which is the licence to report it moved instead
        of tuning the sampler until it agreed. Both numbers are asserted: the one that
        holds, and the one that does not.

        The measured figure is the *second* one this build has recorded — it was 0.71
        until compressing the archetype affinities closed the anti-fingerprint gap.
        That is the tolerance doing its job rather than a defect: ``abs=0.03`` is wide
        enough to absorb sampling noise and narrow enough that a five-point structural
        move reddens this test and forces the knob's rationale to be rewritten, which
        is exactly what happened.
        """
        realised = self._aggregate_cross_check()

        assert realised == pytest.approx(P_ANY_CONDITION_MEASURED.value, abs=0.03), (
            f"aggregate true prevalence is now {realised:.4f}; "
            f"P_ANY_CONDITION_MEASURED records {P_ANY_CONDITION_MEASURED.value}"
        )
        assert realised > P_ANY_CONDITION_EXPECTED.value + 0.05, (
            "the aggregate has come back down to the design record's 0.55. If the "
            "per-condition marginals still match their sources, this is a genuine "
            "discovery and P_ANY_CONDITION_EXPECTED's falsification note is now wrong"
        )

    @staticmethod
    def _shape_blocks() -> dict[tuple[str, ...], list[Any]]:
        """The cross-check's cohort, kept as blocks so its shape can be inspected."""
        return {
            parts: _sample(
                AGGREGATE_PROBE_PER_SHAPE,
                base=9_600_000 + index * 10_000,
                parts=parts,
            )
            for index, parts in enumerate(REALISTIC_PART_SETS)
        }

    @classmethod
    def _aggregate_cross_check(cls) -> float:
        cohort = [history for block in cls._shape_blocks().values() for history in block]
        return sum(1 for history in cohort if history.conditions) / len(cohort)

    def test_the_cross_check_cohort_is_the_plan_its_provenance_names(self) -> None:
        """Round 6, finding 1. The sampling plan, measured rather than remembered.

        ``P_ANY_CONDITION_MEASURED`` said 21,000 cases. The probe drew 1,500 across
        each of seven shapes — 10,500 — and the constant had been carrying the wrong
        figure for as long as it had existed. Nothing computed the number, so nothing
        could disagree with it.

        Both halves are pinned here: the cohort really is
        ``AGGREGATE_PROBE_PER_SHAPE`` per shape across every shape, and the knob's own
        prose has to say so. A future change to either alone fails.
        """
        blocks = self._shape_blocks()

        assert set(blocks) == set(REALISTIC_PART_SETS), (
            "the cross-check no longer covers every realistic claim shape"
        )
        for parts, block in blocks.items():
            assert len(block) == AGGREGATE_PROBE_PER_SHAPE, (
                f"shape {parts} contributed {len(block)} cases, not the declared "
                f"{AGGREGATE_PROBE_PER_SHAPE} — the weighting is no longer "
                f"{AGGREGATE_PROBE_WEIGHTING!r}"
            )
        total = sum(len(block) for block in blocks.values())
        assert total == AGGREGATE_PROBE_N, (
            f"the cross-check drew {total} cases against a declared {AGGREGATE_PROBE_N}"
        )

    def test_the_knob_states_the_plan_it_was_actually_measured_under(self) -> None:
        """The provenance is checked against the arithmetic, not proofread.

        A ``Knob``'s ``source`` is the only record of how its value was arrived at, and
        it is prose — which is exactly the material this package has learned not to
        trust. So the count in it is asserted against the computed one, and the
        weighting word against the constant that governs the loop.
        """
        source = P_ANY_CONDITION_MEASURED.source
        assert f"{AGGREGATE_PROBE_N:,}" in source, (
            f"the knob's source does not state the {AGGREGATE_PROBE_N:,} cases the "
            f"cross-check actually draws: {source!r}"
        )
        assert AGGREGATE_PROBE_WEIGHTING in source, (
            f"the knob's source does not state the {AGGREGATE_PROBE_WEIGHTING!r} "
            "weighting, so a reader cannot tell it apart from the reference population"
        )
        assert "cross-check" in source.lower(), (
            "the knob still presents itself as something other than the sampled "
            "cross-check it is"
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

    def test_a_prior_claim_cannot_postdate_the_current_injury(self) -> None:
        """Finding 3. "Prior" is a claim about order, so the order is enforced.

        Nothing checked it. A claim dated after the current injury loaded cleanly,
        derived into the ledger as a prior claim, and every §4664 and Benson hook
        downstream would have read it as predating the injury it postdates.
        """
        with pytest.raises(Exception, match="does not precede the current injury"):
            parse_case_seed(
                _seed_body(
                    886,
                    scenario={
                        "prior_claims": [
                            {
                                "body_parts": ["lumbar_spine"],
                                "date_of_injury": "2023-06-01",
                                "resolution_type": "c_and_r",
                            }
                        ]
                    },
                )
            )

    def test_a_prior_claim_on_the_day_of_the_current_injury_is_refused(self) -> None:
        """Strictly before, and the boundary is where a loose check would pass.

        Two claims arising the same day are not a prior and a current; they are one
        event pleaded twice, or a data error. Either way the seed is wrong, and
        ``<=`` would have admitted it.
        """
        with pytest.raises(Exception, match="does not precede the current injury"):
            parse_case_seed(
                _seed_body(
                    887,
                    scenario={
                        "prior_claims": [
                            {
                                "body_parts": ["lumbar_spine"],
                                "date_of_injury": "2022-04-11",
                                "resolution_type": "stipulated_award",
                            }
                        ]
                    },
                )
            )

    def test_a_prior_claim_may_still_be_resolving_when_the_current_one_arises(self) -> None:
        """The half that must stay legal, and the reason the check is on one field.

        Prior claims that are still open when the new injury happens are ordinary —
        a 2019 injury resolving in 2023 is a slow but unremarkable file, and an open
        prior claim is precisely the fact pattern §4664 apportionment arguments turn
        on. Only the *injury* date carries the ordering claim; the resolution date,
        the award date and the claim's status carry none of it.
        """
        seed = parse_case_seed(
            _seed_body(
                888,
                scenario={
                    "prior_claims": [
                        {
                            "body_parts": ["lumbar_spine"],
                            "date_of_injury": "2019-03-02",
                            "resolution_date": "2023-11-14",
                            "resolution_type": "stipulated_award",
                            "award": {
                                "body_parts": ["lumbar_spine"],
                                "pd_percent": 15,
                                "award_date": "2023-12-01",
                            },
                        }
                    ]
                },
            )
        )
        claims = seed.scenario.medical_history.prior_claims
        assert claims[0].resolution_date > seed.injury.onset_date
        assert claims[0].award.award_date > seed.injury.onset_date

    def test_a_prior_claim_inside_a_cumulative_trauma_window_is_allowed(self) -> None:
        """The deliberate permissiveness, asserted so it reads as a decision.

        A cumulative trauma is an exposure *period*, and the check compares against
        ``onset_date`` — which for CT is ``ct_end``, the later bound. So a specific
        injury arising in the middle of an ongoing exposure period is admitted. That
        is right: a worker whose back is accumulating damage over three years can
        also drop a crate on their foot in year two, and refusing that would reject a
        real fact pattern in order to tidy an edge. What the check rejects is only
        what is impossible — a prior claim arising after the current injury has run
        its course.
        """
        body = _seed_body(889, parts=("lumbar_spine",))
        body["injury"] = {
            "type": "cumulative_trauma",
            "ct_start": "2020-01-06",
            "ct_end": "2023-01-06",
            "body_parts": [{"part": "lumbar_spine"}],
        }
        body["scenario"]["medical_history"] = {
            "prior_claims": [
                {
                    "body_parts": ["knee"],
                    "date_of_injury": "2021-08-30",
                    "resolution_type": "c_and_r",
                }
            ]
        }
        seed = parse_case_seed(body)
        claim = seed.scenario.medical_history.prior_claims[0]
        assert claim.date_of_injury > seed.injury.ct_start
        assert claim.date_of_injury < seed.injury.onset_date

    def test_a_denied_claim_cannot_carry_an_award(self) -> None:
        """Finding 3a. The contradiction could be written by typing nothing.

        ``PriorAwardEntry.resolution_type`` used to default to ``stipulated_award``,
        so a denied claim with an award block loaded cleanly, derived into the ledger,
        and grounded a SIBTF hook on the Fund's own argument against liability.
        """
        with pytest.raises(Exception, match="produced no permanent disability to award"):
            parse_case_seed(
                _seed_body(
                    892,
                    scenario={
                        "prior_claims": [
                            {
                                "body_parts": ["lumbar_spine"],
                                "date_of_injury": "2015-01-05",
                                "resolution_type": "denied",
                                "award": {
                                    "body_parts": ["lumbar_spine"],
                                    "pd_percent": 12,
                                    "award_date": "2016-02-01",
                                },
                            }
                        ]
                    },
                )
            )

    def test_a_pending_claim_cannot_carry_an_award_either(self) -> None:
        with pytest.raises(Exception, match="produced no permanent disability to award"):
            parse_case_seed(
                _seed_body(
                    893,
                    scenario={
                        "prior_claims": [
                            {
                                "body_parts": ["knee"],
                                "date_of_injury": "2015-01-05",
                                "resolution_type": "pending",
                                "award": {
                                    "body_parts": ["knee"],
                                    "pd_percent": 8,
                                    "award_date": "2016-02-01",
                                },
                            }
                        ]
                    },
                )
            )

    def test_an_award_cannot_have_issued_out_of_a_different_resolution(self) -> None:
        with pytest.raises(Exception, match="cannot have issued out of two"):
            parse_case_seed(
                _seed_body(
                    894,
                    scenario={
                        "prior_claims": [
                            {
                                "body_parts": ["lumbar_spine"],
                                "date_of_injury": "2015-01-05",
                                "resolution_type": "c_and_r",
                                "award": {
                                    "body_parts": ["lumbar_spine"],
                                    "pd_percent": 12,
                                    "award_date": "2016-02-01",
                                    "resolution_type": "stipulated_award",
                                },
                            }
                        ]
                    },
                )
            )

    def test_an_unstated_award_resolution_inherits_the_claims(self) -> None:
        """The other half of the same fix: silence is not a contradiction.

        An award is *how the claim resolved*, so the seed no longer defaults it to a
        value that can disagree — it defaults to the claim's own.
        """
        seed = parse_case_seed(
            _seed_body(
                895,
                scenario={
                    "prior_claims": [
                        {
                            "body_parts": ["lumbar_spine"],
                            "date_of_injury": "2015-01-05",
                            "resolution_type": "c_and_r",
                            "award": {
                                "body_parts": ["lumbar_spine"],
                                "pd_percent": 12,
                                "award_date": "2016-02-01",
                            },
                        }
                    ]
                },
            )
        )
        assert seed.scenario.medical_history.prior_claims[0].award.resolution_type is None
        history = derive_medical_history(
            seed, None, date_of_birth=applicant_date_of_birth(seed)
        )
        assert history.awards[0].resolution_type == "c_and_r", (
            "the ledger should carry the resolved value so no consumer has to know "
            "the seed left it unstated"
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


class TestTheSibtfPredicateMeansWhatItSays:
    """Finding 4. The remediation text and the check were two different rules.

    ``sibtf``'s message offered two edits — "add a prior_claims entry, or a condition
    predating the injury" — and the predicate honoured only the first. Following the
    second changed nothing, which is the failure mode the whole message registry
    (ISC-129) exists to make impossible; it slipped through because the registry
    checks *seed* messages and this one is a plan warning.

    Worse in the other direction: any prior claim silenced it, including a denied one
    that produced no disability at all. Labor Code §4751 is about a pre-existing
    permanent **disability** the Fund could be liable for, so a claim the applicant
    lost grounds nothing.

    One predicate now answers both — :func:`sibtf_grounding` — and the warning text is
    generated from the same source it evaluates.
    """

    def _plan(self, scenario: dict[str, Any]) -> Any:
        body = _seed_body(891, scenario=scenario)
        body["lifecycle"] = {
            "target_stage": "pre_trial",
            "eval_type": "qme",
            "doctrine_hooks": ["sibtf"],
        }
        body["injury"]["date_of_injury"] = "2020-04-11"
        return build_case_plan(parse_case_seed(body))

    @staticmethod
    def _warned(plan: Any) -> bool:
        return any("sibtf" in w and "world-truth ledger" in w for w in plan.warnings)

    def test_a_qualifying_predating_condition_grounds_it(self) -> None:
        """Witness 1: the edit the message offered and the predicate ignored."""
        plan = self._plan(
            {
                "sample_conditions": False,
                "conditions": [
                    {
                        "label": "lumbar degenerative disc disease",
                        "key": "lumbar_disc_degeneration",
                        "severity": "severe",
                        "symptomatic_before_doi": True,
                    }
                ],
            }
        )
        assert not self._warned(plan)

    def test_a_qualifying_prior_award_grounds_it(self) -> None:
        """Witness 2: an adjudicated prior PD is the paradigm §4751 fact."""
        plan = self._plan(
            {
                "sample_conditions": False,
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
                ],
            }
        )
        assert not self._warned(plan)

    def test_a_denied_claim_with_no_disability_does_not_silence_it(self) -> None:
        """Witness 3: the direction the old predicate got wrong.

        A denied claim is the Fund's argument *against* liability, not evidence for
        it. Under the old rule its mere presence silenced the warning.
        """
        plan = self._plan(
            {
                "sample_conditions": False,
                "prior_claims": [
                    {
                        "body_parts": ["lumbar_spine"],
                        "date_of_injury": "2015-01-05",
                        "resolution_type": "denied",
                    }
                ],
            }
        )
        assert self._warned(plan)

    def test_a_pending_claim_with_no_disability_does_not_silence_it(self) -> None:
        plan = self._plan(
            {
                "sample_conditions": False,
                "prior_claims": [
                    {
                        "body_parts": ["knee"],
                        "date_of_injury": "2016-02-02",
                        "resolution_type": "pending",
                    }
                ],
            }
        )
        assert self._warned(plan)

    def test_a_resolved_condition_does_not_qualify(self) -> None:
        """Finding 3b. A factor that stopped operating cannot combine with anything.

        §4751 asks whether a pre-existing disability *combines* with the new injury to
        produce a greater one. This module defines ``resolved`` as no longer a live
        factor, so a severe condition that resolved before the injury grounds no more
        than no condition at all — and the old predicate accepted it, because it read
        severity and symptom history and never looked at trajectory.

        Severity is ``severe`` here so the trajectory clause is the only thing keeping
        the warning up. At ``moderate`` this test would pass on the severity bar alone
        and prove nothing about trajectory.
        """
        plan = self._plan(
            {
                "sample_conditions": False,
                "conditions": [
                    {
                        "label": "resolved lumbar strain with degenerative change",
                        "key": "lumbar_disc_degeneration",
                        "severity": "severe",
                        "symptomatic_before_doi": True,
                        "trajectory": "resolved",
                    }
                ],
            }
        )
        assert self._warned(plan)

    def test_the_same_condition_still_running_does_qualify(self) -> None:
        """The matched control: trajectory is the only thing that moved."""
        plan = self._plan(
            {
                "sample_conditions": False,
                "conditions": [
                    {
                        "label": "lumbar degenerative disc disease",
                        "key": "lumbar_disc_degeneration",
                        "severity": "severe",
                        "symptomatic_before_doi": True,
                        "trajectory": "progressive",
                    }
                ],
            }
        )
        assert not self._warned(plan)

    def test_a_moderate_condition_no_longer_qualifies(self) -> None:
        """Counsel's ruling, and the witness it flipped [counsel-confirmed 2026-08-10].

        This case grounded SIBTF until counsel read the line and called
        moderate-or-worse too loose. Everything else about the condition is what the
        predicate wants — symptomatic before the injury, still progressing, on a region
        the claim names — so severity is the only thing refusing it, which is what
        makes this the witness for the ruling rather than a restatement of the others.

        The *direction* is confirmed and the exact §4751 threshold is not: it is an
        open counsel item for M2. Severe is the conservative reading, because a warning
        that fires when it need not costs an author a sentence, and a hook standing on
        evidence that does not support it costs the corpus its coherence.
        """
        plan = self._plan(
            {
                "sample_conditions": False,
                "conditions": [
                    {
                        "label": "lumbar degenerative disc disease",
                        "key": "lumbar_disc_degeneration",
                        "severity": "moderate",
                        "symptomatic_before_doi": True,
                        "trajectory": "progressive",
                    }
                ],
            }
        )
        assert self._warned(plan)

    def test_the_qualifying_grade_is_the_one_counsel_confirmed(self) -> None:
        """The knob itself, so a widening has to be a deliberate edit with a reason."""
        assert frozenset({"severe"}) == SIBTF_DISABLING_SEVERITIES, (
            "the qualifying severity set has moved off counsel's ruling; widening it "
            "is a legal decision, not a tuning knob"
        )

    def test_an_asymptomatic_incidental_finding_does_not_qualify(self) -> None:
        """The boundary the severity clause draws, asserted so it is not an accident.

        Every degenerative finding in the catalog comes from a study of *asymptomatic*
        people — that is what those prevalence tables measured. A radiographic finding
        nobody felt is not a pre-existing permanent disability, and a predicate that
        accepted one would ground SIBTF on roughly half the corpus.
        """
        plan = self._plan(
            {
                "sample_conditions": False,
                "conditions": [
                    {
                        "label": "cervical disc bulge",
                        "key": "cervical_disc_bulge",
                        "severity": "subclinical",
                        "symptomatic_before_doi": False,
                    }
                ],
            }
        )
        assert self._warned(plan)

    def test_the_warning_text_is_generated_from_the_predicate_it_evaluates(self) -> None:
        """The structural half of the fix, and the reason finding 4 existed.

        Two independently maintained descriptions of one rule will drift, and this
        pair drifted before anybody ran it. So the remediation text is now built from
        :data:`SIBTF_QUALIFYING`, the same tuple the predicate reads.
        """
        plan = self._plan({"sample_conditions": False})
        warning = next(w for w in plan.warnings if "sibtf" in w)
        for clause in SIBTF_QUALIFYING:
            assert clause.remediation in warning, (
                f"the sibtf warning does not offer {clause.remediation!r}, so the text "
                "and the predicate have come apart again"
            )
        assert HOOK_GROUNDING["sibtf"] == sibtf_requirement()


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
