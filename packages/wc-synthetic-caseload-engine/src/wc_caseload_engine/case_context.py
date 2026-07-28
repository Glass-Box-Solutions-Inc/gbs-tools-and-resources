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

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import structlog

from wc_caseload_engine.determinism import pin_substrate_clock
from wc_caseload_engine.lifecycle_bridge import CaseTimeline, seed_to_case_parameters
from wc_caseload_engine.name_denylist import warn_if_denylisted
from wc_caseload_engine.seeds import ANCHOR_DATE, CaseSeed, derive_seed
from wc_caseload_engine.substrate import SubstrateUnavailableError, import_substrate

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

PROVENANCE_SEED_DENYLISTED = "seed_denylisted"
"""Cast field declared in the seed that matches the real-organization denylist.

Deliberately *outside* :data:`SYNTHETIC_PROVENANCE`. The name is still kept —
the seed is the contract and a seeder naming a party may mean it — but the
engine has identified it as real, and a manifest that went on asserting
``zeroRealPii: true`` over the engine's own detection would be asserting
something the engine knows to be false. The warning used to live only in the
log; a corpus does not ship with the log.
"""

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

_ORGANIZATION_STEMS: tuple[str, ...] = (
    "Ashvale",
    "Bellhurst",
    "Cordwyn",
    "Dunmarch",
    "Eastmoor",
    "Fallowbrook",
    "Grimsby Hollow",
    "Hallowmere",
    "Ironvale",
    "Juniper Reach",
    "Kestrelford",
    "Lowfell",
    "Mendlebury",
    "Netherby",
    "Oakhaven",
    "Pinecross",
    "Quillhaven",
    "Redmarch",
    "Stonebridge Vale",
    "Thistledown",
    "Underhill",
    "Vantry",
    "Westmarsh",
    "Yarrowfield",
)
"""Coined place-stems shared by employers and medical facilities.

Same reasoning as :data:`_CARRIER_STEMS`: invented rather than drawn from a
real-place list, because a plausible Californian place name is exactly how a
real employer or a real clinic is named.
"""

_EMPLOYER_SUFFIXES_BY_INDUSTRY: Mapping[str, tuple[str, ...]] = {
    "government": (
        "Municipal Services District",
        "Regional Public Works Authority",
        "County Services Authority",
    ),
    "manufacturing": (
        "Manufacturing Company",
        "Industrial Works, Inc.",
        "Fabrication Company",
    ),
    "construction": ("Construction Group", "Builders, Inc.", "Contracting Company"),
    "healthcare": ("Health Partners", "Medical Group", "Care Network"),
    "warehouse_logistics": (
        "Logistics Company",
        "Distribution Center",
        "Freight Services, Inc.",
    ),
    "retail_service": ("Retail Group", "Markets, Inc.", "Stores Company"),
}
"""Coined employer suffixes, chosen to match the industry the substrate drew.

The substrate picks ``(industry, company, position)`` as one unit, and the
industry and the position stay — a Sheriff's Deputy at a coined *retail* chain
would be a worse document than a real employer name is a risk. Only the
company is replaced, with a suffix that keeps the trio coherent.
"""

_EMPLOYER_SUFFIXES_DEFAULT: tuple[str, ...] = (
    "Industries, Inc.",
    "Enterprises, Inc.",
    "Services Company",
)
"""Used when the substrate's industry key is one this table does not know."""

_FACILITY_SUFFIXES: tuple[str, ...] = (
    "Orthopedic & Spine Center",
    "Medical Group",
    "Pain Management Clinic",
    "Rehabilitation Center",
    "Diagnostic Imaging Center",
    "Neurology Associates",
    "Physical Therapy Associates",
    "Occupational Health Center",
)
"""Coined medical-facility suffixes covering the specialties the substrate uses."""


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
    warnings: tuple[str, ...] = ()
    """Anything the cast build found worth surfacing to the manifest.

    Today that is exactly one thing: a seed-declared name that matched the
    real-organization denylist. It travels to ``plan.warnings`` and from there
    into ``manifest.warnings``, because a finding that lives only in a log is
    not shipped with the corpus the log describes.
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


def synthetic_employer_name(seed: CaseSeed, industry: str) -> str:
    """A coined employer name for *industry*, stable for a given seed."""
    rng = seed.rng(f"employer:{industry}")
    suffixes = _EMPLOYER_SUFFIXES_BY_INDUSTRY.get(industry, _EMPLOYER_SUFFIXES_DEFAULT)
    return f"{rng.choice(_ORGANIZATION_STEMS)} {rng.choice(suffixes)}"


def synthetic_facility_name(seed: CaseSeed, salt: str) -> str:
    """A coined medical-facility name, stable for a given seed and *salt*."""
    rng = seed.rng(f"facility:{salt}")
    return f"{rng.choice(_ORGANIZATION_STEMS)} {rng.choice(_FACILITY_SUFFIXES)}"


def _industry_key(case: Any) -> str:
    """Recover the industry key from the employer as it currently stands.

    ``FakeDataGenerator`` stores the industry as ``department``, title-cased
    with underscores expanded (``warehouse_logistics`` -> ``Warehouse
    Logistics``). Reversing that is enough to pick a coherent coined suffix, and
    an unrecognized value simply falls through to the neutral pool.

    Reads ``department`` deliberately rather than taking the key as an argument:
    :func:`_apply_seed_industry` has already written the seed's industry there
    if the seed named one, so there is exactly one place the industry lives and
    one answer to what it is.
    """
    department = str(getattr(case.employer, "department", "") or "")
    return department.strip().lower().replace(" ", "_")


def employer_suffixes_for_industry(industry: str) -> tuple[str, ...]:
    """The coined-name suffixes that keep an employer coherent with *industry*.

    Exposed because the coherence regression has to assert against the same
    table the coining uses; a test carrying its own copy would pass while the
    two drifted apart.
    """
    return _EMPLOYER_SUFFIXES_BY_INDUSTRY.get(
        _normalize_industry(industry), _EMPLOYER_SUFFIXES_DEFAULT
    )


def _normalize_industry(industry: str) -> str:
    """``profile.employer.industry`` in the substrate's own key form."""
    return industry.strip().lower().replace(" ", "_")


def _substrate_positions_for(industry_key: str) -> tuple[str, ...]:
    """Job titles the substrate associates with *industry_key*, in file order.

    Read live from ``data.wc_constants`` rather than copied here, for the same
    reason the denylist reads the organization pools live: a copy is a snapshot
    that stops matching the substrate the moment the substrate is updated, and
    nothing would report the drift.

    Ordering is the pool's own list order — never a ``set``, whose iteration
    order is salted per process (see :mod:`wc_caseload_engine.determinism`).
    """
    try:
        constants = import_substrate("data.wc_constants")
    except SubstrateUnavailableError:  # pragma: no cover - cast needs the substrate
        return ()
    entries = getattr(constants, "EMPLOYER_TEMPLATES", {}).get(industry_key, ())
    return tuple(position for _company, position in entries)


def _apply_seed_industry(case: Any, seed: CaseSeed) -> None:
    """Apply the seed's employer industry *before* anything derives from it.

    The substrate draws ``(industry, company, position)`` from one pool row, so
    the trio is coherent by construction — until something replaces one member
    of it. The seed's ``profile.employer.industry`` did, and it landed too late:
    the coined company suffix and the position were both derived from the
    substrate's *pre-override* industry while only ``department`` carried the
    seed's. ``rng_seed=2`` with ``industry: healthcare`` produced a construction
    company name, a healthcare department and a construction job title — one
    employer, two industries, and a document set that reads as three different
    people's files.

    Applying the industry first is the whole fix: the department is the seed's,
    the position is re-drawn from the *seeded* industry's titles, and
    :func:`_replace_real_organizations` then coins a name from the same
    industry because :func:`_industry_key` reads what this wrote.

    The re-drawn position is a job title, never a company, so nothing here
    reintroduces a pooled organization name — the coining sweep still owns every
    organization on the case. A seed naming ``applicant.occupation`` outranks
    this: ``_apply_profile_overrides`` runs afterwards, and the more specific
    field wins.
    """
    industry = seed.profile.employer.industry
    if not industry:
        return

    case.employer.department = industry
    positions = _substrate_positions_for(_normalize_industry(industry))
    if not positions:
        # A free-text industry the substrate has no titles for. The department
        # is still the seed's and the name still falls through to the neutral
        # suffix pool; inventing a job title would be worse than keeping the
        # substrate's, which is at least a real occupation.
        log.debug("cast.industry_positions_unknown", industry=industry, case_id=seed.case_id)
        return
    case.employer.position = seed.rng(f"position:{_normalize_industry(industry)}").choice(
        positions
    )


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
    """Swap **every** substrate organization draw for a coined name.

    ``data/wc_constants.py`` holds four pools that name organizations, and all
    four reach the cast:

    ================== ======================================================
    Pool               Real entities it contains
    ================== ======================================================
    INSURANCE_CARRIERS State Fund, Zenith, Liberty Mutual, Sedgwick
    DEFENSE_FIRMS      Bradford & Barthel, Laughlin Falbo, Hanna Brophy
    ALL_EMPLOYERS      Safeway, Costco, Kaiser Permanente, UPS, City of LA
    MEDICAL_FACILITIES clinic names for the treating, QME and prior providers
    ================== ======================================================

    Realistic, and exactly the wrong kind of realistic: a fabricated claim file
    naming a real employer is a real-world collision whatever the folder says
    about being synthetic — and it is worse than a real carrier, because the
    employer is a *named defendant* in the caption of every legal document.

    Covering only the first two pools is the defect this replaced. ``Safeway
    Inc.`` was appearing as the defendant on Applications for Adjudication
    under a manifest asserting ``zeroRealPii: true``, because the employer was
    classed as a Faker draw when it was really a pool draw.

    The substrate is a library we do not edit, so the substitution happens here,
    on the generated case object, before any template reads it. A seed that
    names its own organization is untouched — the seed is the contract — but it
    is checked against the denylist and warned about, so a deliberate real name
    is visible rather than silent.

    Returns:
        The provenance entries for the fields this function owned.
    """
    provenance: dict[str, str] = {}
    profile = seed.profile

    if not profile.carrier.name:
        case.insurance.carrier_name = synthetic_carrier_name(seed)
        case.insurance.adjuster_email = _contact_email(
            case.insurance.adjuster_name, case.insurance.carrier_name
        )
        provenance["carrier"] = PROVENANCE_ENGINE

    if not profile.attorneys.defense_firm:
        case.insurance.defense_firm = synthetic_firm_name(seed, "defense_firm")
        case.insurance.defense_email = _contact_email(
            case.insurance.defense_attorney, case.insurance.defense_firm
        )
        provenance["defenseFirm"] = PROVENANCE_ENGINE

    if not profile.employer.name:
        case.employer.company_name = synthetic_employer_name(seed, _industry_key(case))
        provenance["employer"] = PROVENANCE_ENGINE

    # Facilities are never seed-declarable — the seed picks specialties, not
    # clinics — so every one of them is coined, unconditionally.
    for label, physician in _facility_bearers(case):
        physician.facility = synthetic_facility_name(seed, label)
        provenance[f"{label}Facility"] = PROVENANCE_ENGINE

    return provenance


def _facility_bearers(case: Any) -> list[tuple[str, Any]]:
    """``(provenance label, physician)`` for every facility-bearing provider.

    Prior providers are included because the substrate draws their clinics from
    the same pool and a medical chronology lists them by name; a sweep that
    stopped at the treating physician would leave the longest document in the
    file unswept.
    """
    bearers: list[tuple[str, Any]] = [("treating", case.treating_physician)]
    if getattr(case, "qme_physician", None) is not None:
        bearers.append(("qme", case.qme_physician))
    for index, provider in enumerate(getattr(case, "prior_providers", ()) or ()):
        bearers.append((f"priorProvider{index}", provider))
    return bearers


_DENYLIST_FIELD_TO_PROVENANCE: Mapping[str, str] = {
    "profile.employer.name": "employer",
    "profile.carrier.name": "carrier",
    "profile.attorneys.applicant_firm": "applicantFirm",
    "profile.attorneys.defense_firm": "defenseFirm",
    "profile.applicant.name": "applicant",
}
"""Seed field path -> the ``castProvenance`` key a hit on it must demote."""


def _warn_on_seed_declared_real_names(seed: CaseSeed) -> tuple[tuple[str, ...], frozenset[str]]:
    """Check every seed-declared organization against the denylist.

    Seed-declared names are kept: the seed is the contract, and a seeder naming
    a party is the one channel where a real name could be intentional. What the
    engine owes is visibility, and the previous version of that debt was paid in
    the log alone — the return value was discarded, so a detected hit left
    ``castProvenance`` reading ``seed`` and the manifest went on claiming
    ``zeroRealPii: true`` about a name the engine had just identified as real.

    Returns:
        ``(warnings, provenance keys to demote)``. The warnings reach
        ``plan.warnings`` and from there the manifest; the keys are recorded as
        :data:`PROVENANCE_SEED_DENYLISTED`, which computes ``zeroRealPii`` false.
    """
    profile = seed.profile
    declared = (
        ("profile.employer.name", profile.employer.name),
        ("profile.carrier.name", profile.carrier.name),
        ("profile.attorneys.applicant_firm", profile.attorneys.applicant_firm),
        ("profile.attorneys.defense_firm", profile.attorneys.defense_firm),
        ("profile.applicant.name", profile.applicant.name),
    )
    warnings: list[str] = []
    demoted: set[str] = set()
    for field_path, value in declared:
        if not value:
            continue
        hits = warn_if_denylisted(value, field=field_path, case_id=seed.case_id)
        if not hits:
            continue
        demoted.add(_DENYLIST_FIELD_TO_PROVENANCE[field_path])
        warnings.append(
            f"{field_path} = {value!r} matches the real-organization denylist "
            f"({', '.join(sorted(hits))}); the seed-declared name is kept, and "
            "provenance.zeroRealPii is therefore false for this case"
        )
    return tuple(warnings), frozenset(demoted)


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
    # ``profile.employer.industry`` is deliberately *not* applied here — it is
    # applied by ``_apply_seed_industry`` before the coining sweep, because the
    # coined name and the position both derive from it. Setting it here as well
    # was the bug: by this point the derivations had already happened.
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


def _cast_provenance(
    seed: CaseSeed,
    engine_owned: Mapping[str, str],
    denylisted: Collection[str] = (),
) -> dict[str, str]:
    """Classify where every identity-bearing cast field came from.

    Three channels, and the distinction is the whole content of the
    ``zeroRealPii`` claim: a field the seed states is synthetic on the seed
    author's word, a field Faker drew is synthetic by construction, and a field
    this module coined replaced a substrate constant that named a real body.

    ``employer`` is classified from ``engine_owned`` rather than defaulted to
    Faker. Calling it a Faker draw was the bookkeeping error behind the
    real-employer leak: the substrate draws employers from a *pool*, not from
    Faker, so the field was vouched for by a claim that was never true of it.
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
    # Last word, deliberately: a seed-declared name the denylist matched is not
    # vouched for by anything, so it overrides both the ``seed`` classification
    # above and any coining recorded in ``engine_owned``.
    for field_name in sorted(denylisted):
        provenance[field_name] = PROVENANCE_SEED_DENYLISTED
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
    denylist_warnings, denylisted_fields = _warn_on_seed_declared_real_names(seed)
    # Order is load-bearing: the industry decides the coined employer suffix and
    # the position, so the seed's industry has to land before the coining sweep
    # reads it. Applying it afterwards (with the rest of the overrides) left the
    # name and the position derived from the industry the *substrate* drew.
    _apply_seed_industry(case, seed)
    engine_owned = _replace_real_organizations(case, seed)
    _apply_profile_overrides(case, seed, timeline)
    _apply_injury_overrides(case, seed, adj_number)

    applicant_firm = seed.profile.attorneys.applicant_firm or DEFAULT_APPLICANT_FIRM
    provenance = _cast_provenance(seed, engine_owned, denylisted_fields)

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
        warnings=denylist_warnings,
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
    "PROVENANCE_SEED_DENYLISTED",
    "SYNTHETIC_PROVENANCE",
    "CaseCast",
    "build_case_cast",
    "synthetic_carrier_name",
    "synthetic_firm_name",
]
