"""One canonical cast per case — built once, used by every document.

Narrative coherence is what separates a case *file* from a pile of PDFs. The
applicant's name, the ADJ number, the date of injury, the employer and the
carrier must be identical in all ninety documents, or the file reads as noise.

So the cast is constructed exactly once per case, from
``seed.rng("cast")``, and every renderer call receives the same object.

The substrate's :class:`FakeDataGenerator` supplies the realistic scaffolding
(addresses, adjuster names, venues, judges, licence numbers). Everything the
seed actually specifies is then overwritten onto it — the seed is the contract,
Faker only fills the silence.

Determinism warning encoded here: ``FakeDataGenerator.__init__`` seeds the
*global* :mod:`random` module and the global Faker instance, and the substrate's
templates draw from that same global stream. Constructing the generator per
case (rather than once per run) is therefore load-bearing: it re-pins the global
stream before each case, so a case renders identically no matter what ran
before it.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import structlog

from wc_caseload_engine.lifecycle_bridge import CaseTimeline, seed_to_case_parameters
from wc_caseload_engine.seeds import ANCHOR_DATE, CaseSeed, derive_seed
from wc_caseload_engine.substrate import import_substrate

log = structlog.get_logger(__name__)

DEFAULT_APPLICANT_FIRM = "Martinez & Associates, APC"
"""The substrate's hard-coded applicant-side firm.

``profile.attorneys.applicant_firm`` is recorded in the seed and the manifest,
but the substrate renders this constant on its letterhead (see
``data/docx_styles.py``). Documented as a known limitation rather than patched:
mutating a substrate module's private constants at runtime would be shared
global state across cases.
"""

_ADJ_DIGITS = 8


@dataclass(frozen=True, slots=True)
class CaseCast:
    """The canonical facts of one case, plus the substrate case object."""

    case: Any
    adj_number: str
    applicant_name: str
    employer_name: str
    carrier_name: str
    applicant_firm: str
    defense_firm: str
    date_of_injury: date
    venue: str
    judge_name: str
    treating_physician: str
    qme_physician: str | None

    def manifest_fields(self) -> dict[str, object]:
        """The cast facts a manifest records for cross-document verification."""
        return {
            "adjNumber": self.adj_number,
            "applicant": self.applicant_name,
            "employer": self.employer_name,
            "carrier": self.carrier_name,
            "applicantFirm": self.applicant_firm,
            "defenseFirm": self.defense_firm,
            "dateOfInjury": self.date_of_injury.isoformat(),
            "venue": self.venue,
            "judge": self.judge_name,
        }


def _adj_number(seed: CaseSeed) -> str:
    """``ADJ`` + 8 digits, stable for a given seed."""
    rng = seed.rng("adj")
    return f"ADJ{rng.randrange(10 ** (_ADJ_DIGITS - 1), 10**_ADJ_DIGITS)}"


def _apply_profile_overrides(case: Any, seed: CaseSeed, timeline: CaseTimeline) -> None:
    """Overwrite the generated cast with everything the seed specifies."""
    profile = seed.profile

    applicant = profile.applicant
    if applicant.name:
        parts = applicant.name.split()
        case.applicant.first_name = parts[0]
        case.applicant.last_name = " ".join(parts[1:]) if len(parts) > 1 else ""
        case.applicant.full_name = applicant.name
    if applicant.age is not None:
        case.applicant.date_of_birth = ANCHOR_DATE - timedelta(days=int(applicant.age * 365.25))
    if applicant.occupation:
        case.employer.position = applicant.occupation
    if applicant.tenure_years is not None:
        case.employer.hire_date = timeline.injury_date - timedelta(
            days=int(applicant.tenure_years * 365.25)
        )

    if profile.employer.name:
        case.employer.company_name = profile.employer.name
    if profile.employer.industry:
        case.employer.department = profile.employer.industry
    if profile.employer.county:
        case.venue = profile.employer.county

    if profile.carrier.name:
        case.insurance.carrier_name = profile.carrier.name
    if profile.attorneys.defense_firm:
        case.insurance.defense_firm = profile.attorneys.defense_firm

    if profile.physicians.ptp_specialty:
        case.treating_physician.specialty = profile.physicians.ptp_specialty
    if profile.physicians.qme_specialty and case.qme_physician is not None:
        case.qme_physician.specialty = profile.physicians.qme_specialty

    # The case title is derived in model_post_init; refresh it after renames.
    case.case_title = f"{case.applicant.full_name} v. {case.employer.company_name}"


def _apply_injury_overrides(case: Any, seed: CaseSeed, adj_number: str) -> None:
    """The seed owns the injury: dates, body parts, ICD-10 codes, mechanism."""
    injury = seed.injury
    body_parts = [part.part for part in injury.body_parts]
    icd10 = [part.icd10 for part in injury.body_parts if part.icd10]
    detail = ", ".join(
        f"{part.part} ({part.detail})" if part.detail else part.part for part in injury.body_parts
    )
    mechanism = injury.mechanism
    for generated in case.injuries:
        generated.date_of_injury = injury.onset_date
        generated.body_parts = body_parts
        generated.icd10_codes = icd10
        generated.adj_number = adj_number
        generated.description = f"{injury.type.replace('_', ' ')} injury to {detail}"
        if mechanism and mechanism != "auto":
            generated.mechanism = mechanism
    case.timeline.date_of_injury = injury.onset_date


def build_case_cast(seed: CaseSeed, timeline: CaseTimeline, case_number: int = 1) -> CaseCast:
    """Build the one canonical cast for a case.

    Args:
        seed: the case seed — the contract.
        timeline: dates derived by :func:`~wc_caseload_engine.lifecycle_bridge.build_timeline`.
        case_number: position in the caseload, used for the substrate's internal id.

    Returns:
        A :class:`CaseCast` whose ``case`` attribute is the substrate object the
        templates render against.
    """
    fake_data = import_substrate("data.fake_data_generator")

    params = seed_to_case_parameters(seed)
    params = params.resolve_random(seed.rng("params"))

    # Re-pins the global random/Faker streams the substrate templates share.
    generator = fake_data.FakeDataGenerator(seed=derive_seed(seed.rng_seed, "cast"))
    case = generator.generate_case_from_params(case_number, params)

    adj_number = _adj_number(seed)
    _apply_profile_overrides(case, seed, timeline)
    _apply_injury_overrides(case, seed, adj_number)

    applicant_firm = seed.profile.attorneys.applicant_firm or DEFAULT_APPLICANT_FIRM

    cast = CaseCast(
        case=case,
        adj_number=adj_number,
        applicant_name=case.applicant.full_name,
        employer_name=case.employer.company_name,
        carrier_name=case.insurance.carrier_name,
        applicant_firm=applicant_firm,
        defense_firm=case.insurance.defense_firm,
        date_of_injury=seed.injury.onset_date,
        venue=case.venue,
        judge_name=case.judge_name,
        treating_physician=case.treating_physician.full_name,
        qme_physician=case.qme_physician.full_name if case.qme_physician else None,
    )
    log.debug(
        "cast.built",
        case_id=seed.case_id,
        adj=adj_number,
        applicant=cast.applicant_name,
    )
    return cast


__all__ = ["DEFAULT_APPLICANT_FIRM", "CaseCast", "build_case_cast"]
