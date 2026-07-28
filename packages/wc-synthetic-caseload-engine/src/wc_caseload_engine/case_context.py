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

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import structlog

from wc_caseload_engine.determinism import pin_substrate_clock
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

PROVENANCE_FAKER = "faker"
"""Cast field drawn from the seeded Faker/substrate generator — synthetic by construction."""

PROVENANCE_SEED = "seed"
"""Cast field declared literally in the seed YAML — synthetic by the author's word."""

PROVENANCE_ENGINE = "engine"
"""Cast field coined here, replacing a substrate constant that names a real organization."""

SYNTHETIC_PROVENANCE: frozenset[str] = frozenset(
    {PROVENANCE_FAKER, PROVENANCE_SEED, PROVENANCE_ENGINE}
)
"""Provenance values that support a ``zeroRealPii`` claim.

The flag is only worth carrying if something can make it false. Every channel
into a cast is enumerated here, so a future channel that is *not* provably
synthetic — an imported real file, a scraped roster — flips the manifest
instead of inheriting a hardcoded ``true``.
"""

_CARRIER_STEMS: tuple[str, ...] = (
    "Alderwyn",
    "Brackenridge",
    "Calderport",
    "Draymoor",
    "Fernhollow",
    "Glasspoint",
    "Harrowgate",
    "Innsmere",
    "Kelbrook",
    "Larkfield Reach",
    "Marrowdale",
    "Northwick",
    "Orrinbay",
    "Pellworth",
    "Quarrymede",
    "Ravensgate",
    "Sablecrest",
    "Thornbury Vale",
)
"""Coined place-stems for synthetic carrier names.

Deliberately invented rather than drawn from a real-place list: a synthetic
claim file that names a real insurer is a real-world collision, and a plausible
Californian place name is exactly how a real insurer is named.
"""

_CARRIER_SUFFIXES: tuple[str, ...] = (
    "Compensation Insurance Company",
    "Indemnity Company",
    "Mutual Insurance Company",
    "Casualty & Indemnity Company",
    "Workers' Compensation Insurance Company",
)

_FIRM_SURNAMES: tuple[str, ...] = (
    "Ashgrove",
    "Brendell",
    "Corradine",
    "Delacroix",
    "Ellsworth",
    "Fairbanks",
    "Grimaldi",
    "Havelock",
    "Ingersoll",
    "Jarrow",
    "Kessendale",
    "Lindqvist",
    "Merriweather",
    "Norcross",
    "Ospina",
    "Prentiss",
    "Quillane",
    "Rothwell",
    "Sandoval",
    "Tremaine",
)
"""Coined surnames for synthetic law-firm names — same reasoning as the carriers."""

_FIRM_SUFFIXES: tuple[str, ...] = ("LLP", "APC", "& Associates, APC", "LLP")


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
    provenance: Mapping[str, str] = field(default_factory=dict)
    """Where each identity-bearing cast field came from — see :data:`SYNTHETIC_PROVENANCE`.

    Recorded so ``manifest.provenance.zeroRealPii`` can be *computed*. A literal
    ``true`` asserts the one thing a generator cannot know about itself.
    """

    @property
    def zero_real_pii(self) -> bool:
        """``True`` when every identity in this cast came from a synthetic channel.

        False the moment a cast field arrives by a route the engine cannot
        vouch for. Nothing in the current engine produces that, which is the
        point: the flag now states a checked fact rather than an intention.
        """
        return all(source in SYNTHETIC_PROVENANCE for source in self.provenance.values())

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


_DERIVED_AGE_RANGE = (25, 62)
"""Working-age band for an applicant whose seed does not state an age.

Matches the band ``FakeDataGenerator`` asked Faker for, so derived casts keep the
same shape — only the clock behind them changes.
"""


def _date_of_birth(seed: CaseSeed) -> date:
    """The applicant's date of birth, always seed-derived and never clock-derived.

    Faker's ``date_of_birth`` draws from a window ending at ``datetime.now()``,
    and a seeded Faker does not make that window stable: the same seed produced
    a 1999-08-14 birthday in Los Angeles and 1999-08-15 in Sydney, because the
    two machines disagreed about what day it was. It would equally have moved
    from one day to the next on one machine.

    Faker is left alone — rebinding its ``datetime`` breaks the ``isinstance``
    checks in its own date parser — and the field is simply owned here instead,
    where the anchor already lives. Substrate templates read
    ``case.applicant.date_of_birth``, so overwriting it settles every downstream
    age line in one place.
    """
    stated = seed.profile.applicant.age
    if stated is not None:
        return ANCHOR_DATE - timedelta(days=int(stated * 365.25))
    low, high = _DERIVED_AGE_RANGE
    rng = seed.rng("dob")
    return ANCHOR_DATE - timedelta(days=rng.randint(low * 365, high * 365) + rng.randint(0, 364))


def synthetic_carrier_name(seed: CaseSeed) -> str:
    """A coined insurance carrier name, stable for a given seed."""
    rng = seed.rng("carrier")
    return f"{rng.choice(_CARRIER_STEMS)} {rng.choice(_CARRIER_SUFFIXES)}"


def synthetic_firm_name(seed: CaseSeed, salt: str) -> str:
    """A coined law-firm name, stable for a given seed and *salt*."""
    rng = seed.rng(salt)
    first, second = rng.sample(_FIRM_SURNAMES, 2)
    suffix = rng.choice(_FIRM_SUFFIXES)
    if suffix.startswith("&"):
        return f"{first} {suffix}"
    return f"{first} & {second} {suffix}"


def _contact_email(person: str, organization: str) -> str:
    """Rebuild a contact email so it matches the organization actually named.

    ``FakeDataGenerator`` derives adjuster and defense emails from the pool name
    it drew, so replacing the organization without replacing the address leaves
    a defense attorney at ``@laughlin.com`` writing on another firm's
    letterhead — the leak surviving in the one field nobody rereads.
    """
    parts = [part for part in person.replace(",", " ").split() if part and part != "Esq."]
    local = ".".join(part.lower() for part in parts[:2]) or "contact"
    domain = "".join(char for char in organization.split()[0].lower() if char.isalpha())
    return f"{local}@{domain or 'example'}.com"


def _replace_real_organizations(case: Any, seed: CaseSeed) -> dict[str, str]:
    """Swap the substrate's real carrier and defense-firm draws for coined names.

    ``data/wc_constants.py`` seeds ``INSURANCE_CARRIERS`` and ``DEFENSE_FIRMS``
    with **actual** California workers' compensation insurers and defense firms
    — State Fund, Zenith, Bradford & Barthel, Laughlin Falbo. Realistic, and
    exactly the wrong kind of realistic: a fabricated claim file naming a real
    carrier or a real firm is a real-world collision, whatever the folder says
    about being synthetic.

    The substrate is a library we do not edit, so the substitution happens here,
    on the generated case object, before any template reads it. A seed that
    names its own carrier or firm is untouched — the seed is the contract.

    Returns:
        The provenance entries for the fields this function owned.
    """
    provenance: dict[str, str] = {}

    if not seed.profile.carrier.name:
        case.insurance.carrier_name = synthetic_carrier_name(seed)
        case.insurance.adjuster_email = _contact_email(
            case.insurance.adjuster_name, case.insurance.carrier_name
        )
        provenance["carrier"] = PROVENANCE_ENGINE

    if not seed.profile.attorneys.defense_firm:
        case.insurance.defense_firm = synthetic_firm_name(seed, "defense_firm")
        case.insurance.defense_email = _contact_email(
            case.insurance.defense_attorney, case.insurance.defense_firm
        )
        provenance["defenseFirm"] = PROVENANCE_ENGINE

    return provenance


def _apply_profile_overrides(case: Any, seed: CaseSeed, timeline: CaseTimeline) -> None:
    """Overwrite the generated cast with everything the seed specifies."""
    profile = seed.profile

    applicant = profile.applicant
    if applicant.name:
        parts = applicant.name.split()
        case.applicant.first_name = parts[0]
        case.applicant.last_name = " ".join(parts[1:]) if len(parts) > 1 else ""
        case.applicant.full_name = applicant.name
    case.applicant.date_of_birth = _date_of_birth(seed)
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
        case.insurance.adjuster_email = _contact_email(
            case.insurance.adjuster_name, profile.carrier.name
        )
    if profile.attorneys.defense_firm:
        case.insurance.defense_firm = profile.attorneys.defense_firm
        case.insurance.defense_email = _contact_email(
            case.insurance.defense_attorney, profile.attorneys.defense_firm
        )

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


def _cast_provenance(seed: CaseSeed, engine_owned: Mapping[str, str]) -> dict[str, str]:
    """Classify where every identity-bearing cast field came from.

    Two channels, and the distinction is the whole content of the
    ``zeroRealPii`` claim: a field the seed states is synthetic on the seed
    author's word, a field Faker drew is synthetic by construction, and a field
    this module coined replaced a substrate constant that named a real body.
    """
    profile = seed.profile
    declared = {
        "applicant": bool(profile.applicant.name),
        "employer": bool(profile.employer.name),
        "carrier": bool(profile.carrier.name),
        "applicantFirm": bool(profile.attorneys.applicant_firm),
        "defenseFirm": bool(profile.attorneys.defense_firm),
    }
    provenance = {
        field_name: PROVENANCE_SEED if is_declared else PROVENANCE_FAKER
        for field_name, is_declared in declared.items()
    }
    # Physicians, judges and adjusters are never seed-declared; the seed only
    # picks their specialty.
    provenance["treatingPhysician"] = PROVENANCE_FAKER
    provenance["judge"] = PROVENANCE_FAKER
    provenance["adjuster"] = PROVENANCE_FAKER
    provenance["dateOfBirth"] = PROVENANCE_SEED if profile.applicant.age else PROVENANCE_FAKER
    provenance.update(engine_owned)
    return provenance


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
    # FakeDataGenerator derives hire dates and litigation stages from
    # ``date.today()``; freeze it before the cast exists, not at render time.
    pin_substrate_clock()
    fake_data = import_substrate("data.fake_data_generator")

    params = seed_to_case_parameters(seed)
    params = params.resolve_random(seed.rng("params"))

    # Re-pins the global random/Faker streams the substrate templates share.
    generator = fake_data.FakeDataGenerator(seed=derive_seed(seed.rng_seed, "cast"))
    case = generator.generate_case_from_params(case_number, params)

    adj_number = _adj_number(seed)
    engine_owned = _replace_real_organizations(case, seed)
    _apply_profile_overrides(case, seed, timeline)
    _apply_injury_overrides(case, seed, adj_number)

    applicant_firm = seed.profile.attorneys.applicant_firm or DEFAULT_APPLICANT_FIRM
    provenance = _cast_provenance(seed, engine_owned)

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
        provenance=provenance,
    )
    log.debug(
        "cast.built",
        case_id=seed.case_id,
        adj=adj_number,
        applicant=cast.applicant_name,
    )
    return cast


__all__ = [
    "DEFAULT_APPLICANT_FIRM",
    "PROVENANCE_ENGINE",
    "PROVENANCE_FAKER",
    "PROVENANCE_SEED",
    "SYNTHETIC_PROVENANCE",
    "CaseCast",
    "build_case_cast",
    "synthetic_carrier_name",
    "synthetic_firm_name",
]
