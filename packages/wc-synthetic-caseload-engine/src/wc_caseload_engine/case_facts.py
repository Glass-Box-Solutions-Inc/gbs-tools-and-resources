"""The CaseFacts ledger — one record of what clinically happened in a case.

Before this module, every template that wanted a clinical detail invented one on
the spot. A QME report drew ``random.choice(["MRI", "X-ray", "CT scan"])`` per
body part and asserted imaging that no diagnostic report in the same case had
ever produced; the diagnostic report drew its own modality independently; and
``has_surgery`` gated six document *rules* while reaching no document *content*
at all, so a post-operative progress report described conservative care.

Nothing was wrong with any single draw. What was wrong is that there was no
place for the case to agree with itself. This module is that place: derived once
per case at plan time, read by every fact-aware template, and published in the
manifest so a reader can check the documents against it.

Two design rules hold the guarantee up.

**Namespaced streams.** Every draw here comes from
:func:`~wc_caseload_engine.seeds.derive_seed` under a ``facts:`` prefix, never
from a stream an existing draw already consumes. A case that seeds no
``scenario:`` block and reaches no fact-aware subtype therefore renders byte for
byte as it did at 0.2.0 — the ledger is computed, published, and simply not
consulted.

**The seed wins, the derivation fills in.** Anything ``scenario:`` states is
taken as given. Anything it leaves open is derived, and the derivation
deliberately reproduces the substrate's own prior behaviour where one existed —
the surgery coin is still 35% off the same ``clinical`` stream, so
``has_surgery`` parity holds for every seed written before this block existed.
"""

from __future__ import annotations

import datetime as dt
import random
from datetime import timedelta
from typing import Any, Literal

import structlog
from pydantic import BaseModel, ConfigDict, Field

from wc_caseload_engine.seeds import CaseSeed, derive_seed

log = structlog.get_logger(__name__)


type Modality = Literal["mri", "ct", "xray", "emg", "labs"]
"""The diagnostic vocabulary a ``scenario:`` block may name.

Deliberately small. These are the modalities the substrate's medical templates
can actually render prose for; admitting a value no template can speak would
produce a ledger entry that no document could honour, which is the failure this
module exists to prevent.
"""

MODALITIES: tuple[str, ...] = ("mri", "ct", "xray", "emg", "labs")
"""Runtime mirror of :data:`Modality`, for validation messages and iteration."""

MODALITY_DISPLAY: dict[str, str] = {
    "mri": "MRI",
    "ct": "CT",
    "xray": "X-Ray",
    "emg": "EMG",
    "labs": "Laboratory Studies",
}
"""How each modality is written in a rendered document.

One spelling per modality, in one place, because the coherence harness greps
for these strings — two spellings would make "no document names an absent
modality" unenforceable.
"""

#: Modalities the derivation may draw when the seed does not say.
#:
#: ``labs`` is excluded on purpose: it is orderable in the schema so a seed can
#: state it, but drawing it unprompted would put lab studies in orthopedic files
#: that have no reason to hold them.
_DERIVABLE_MODALITIES: tuple[str, ...] = ("mri", "ct", "xray", "emg")

SURGERY_CPT_CODES: dict[str, tuple[str, str]] = {
    "lumbar_spine": ("63030", "Lumbar laminotomy with decompression"),
    "cervical_spine": ("63075", "Cervical discectomy, anterior approach"),
    "thoracic_spine": ("63055", "Thoracic laminectomy with decompression"),
    "shoulder": ("29827", "Arthroscopic rotator cuff repair"),
    "knee": ("29881", "Arthroscopic partial medial meniscectomy"),
    "wrist": ("64721", "Carpal tunnel release"),
    "ankle": ("27822", "Open treatment of ankle fracture"),
    "elbow": ("24357", "Lateral epicondylitis release"),
}
"""Body part -> (CPT, description) for a surgery the ledger says happened.

The CPT is the single figure the coherence harness checks across documents: an
operative report, a QME's surgical history and a treating physician's plan must
all name the same procedure or the file is describing two different operations.
"""

_DEFAULT_CPT: tuple[str, str] = ("64999", "Unlisted procedure, nervous system")


class DiagnosticFact(BaseModel):
    """One diagnostic study — performed, or deliberately not.

    The *absent* half is the half that makes the ledger enforceable. Recording
    only what happened lets a template invent anything it likes about what did
    not; recording an explicit absence gives the harness something to grep for.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    modality: str
    body_part: str
    date: dt.date | None = None
    performed: bool = True

    @property
    def display(self) -> str:
        """The modality as a rendered document spells it."""
        return MODALITY_DISPLAY.get(self.modality, self.modality.upper())


class SurgeryFact(BaseModel):
    """Whether an operation happened, and if so which one.

    Phase 1 carries ``none`` and ``performed`` only. The ticket's fuller
    vocabulary (``recommended``, ``denied_by_ur``) needs UR-dispute wiring that
    belongs with the treatment phase, and admitting a status no template can
    render would reintroduce exactly the gap this ledger closes.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["none", "performed"] = "none"
    body_part: str | None = None
    cpt_code: str | None = None
    cpt_description: str | None = None
    date: dt.date | None = None

    @property
    def performed(self) -> bool:
        return self.status == "performed"


class ProviderFact(BaseModel):
    """One treating or examining provider.

    Exists so subpoenaed-records packets can be attributed to *different*
    providers. The engine never set ``provider_index``, so every packet in every
    case was attributed to the treating physician — a records subpoena to one
    provider, answered four times by the same clinic.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    specialty: str
    facility: str


class VisitFact(BaseModel):
    """One dated clinical contact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    date: dt.date
    kind: Literal["initial", "follow_up", "post_operative", "final"] = "follow_up"


class CaseFacts(BaseModel):
    """What clinically happened in one case, decided once.

    Derived at plan time by :func:`derive_case_facts` and carried alongside the
    plan, so the planner, the renderer and the manifest all read the same
    answer instead of three independent guesses.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    diagnostics: tuple[DiagnosticFact, ...] = ()
    surgery: SurgeryFact = Field(default_factory=SurgeryFact)
    providers: tuple[ProviderFact, ...] = ()
    visits: tuple[VisitFact, ...] = ()
    mmi_date: dt.date | None = None
    wpi: int | None = None
    pd: int | None = None

    @property
    def performed_diagnostics(self) -> tuple[DiagnosticFact, ...]:
        return tuple(fact for fact in self.diagnostics if fact.performed)

    @property
    def absent_diagnostics(self) -> tuple[DiagnosticFact, ...]:
        return tuple(fact for fact in self.diagnostics if not fact.performed)

    def performed_modalities(self) -> frozenset[str]:
        return frozenset(fact.modality for fact in self.performed_diagnostics)

    def absent_modalities(self) -> frozenset[str]:
        """Absent modalities that are not performed for some *other* body part.

        A study can be performed on the lumbar spine and deliberately absent on
        the shoulder; the modality itself is then not absent from the file, and
        a document naming it is not incoherent. Only a modality that appears
        nowhere as performed is greppable as an absence.
        """
        return frozenset(
            fact.modality for fact in self.absent_diagnostics
        ) - self.performed_modalities()

    def diagnostic_for(self, index: int) -> DiagnosticFact | None:
        """The performed study a document at *index* should report.

        Round-robin rather than modulo-with-repeats-first so that a case with
        three performed studies and three imaging reports emits one of each,
        which is what makes "one document per performed diagnostic" checkable.
        """
        performed = self.performed_diagnostics
        if not performed:
            return None
        return performed[index % len(performed)]

    def provider_for(self, index: int) -> ProviderFact | None:
        """The provider a records packet at *index* is answered by."""
        if not self.providers:
            return None
        return self.providers[index % len(self.providers)]


# ---------------------------------------------------------------------------
# Derivation
# ---------------------------------------------------------------------------


def _rng(seed: CaseSeed, salt: str) -> random.Random:
    """A private stream under the ``facts:`` namespace.

    Never the global :mod:`random` the substrate templates draw from, and never
    a salt an existing draw already uses — that separation is what lets a case
    with no ``scenario:`` block keep its 0.2.0 bytes.
    """
    return random.Random(derive_seed(seed.rng_seed, f"facts:{salt}"))


def _body_parts(seed: CaseSeed) -> list[str]:
    return [part.part for part in seed.injury.body_parts]


def _derive_diagnostics(seed: CaseSeed, timeline: Any) -> tuple[DiagnosticFact, ...]:
    """Ledger entries for every study, performed or deliberately absent.

    The seed's ``scenario.diagnostics`` is authoritative. What it does not
    mention is derived: each body part draws a study with a probability that
    leaves some parts deliberately un-imaged, because a file where every region
    was scanned is exactly the tell this ledger exists to remove.
    """
    scenario = seed.scenario.diagnostics
    parts = _body_parts(seed)
    primary = parts[0] if parts else "spine"
    rng = _rng(seed, "diagnostics")

    onset = getattr(timeline, "injury_date", None) or seed.injury.onset_date
    facts: list[DiagnosticFact] = []
    claimed: set[tuple[str, str]] = set()

    def add(modality: str, body_part: str, *, performed: bool) -> None:
        key = (modality, body_part)
        if key in claimed:
            return
        claimed.add(key)
        study_date = onset + timedelta(days=30 + 25 * len(facts)) if performed else None
        facts.append(
            DiagnosticFact(
                modality=modality,
                body_part=body_part,
                date=study_date,
                performed=performed,
            )
        )

    # Explicit first, so a derived draw can never contradict a seeded statement.
    for entry in scenario.performed:
        add(entry.modality, entry.body_part or primary, performed=True)
    for entry in scenario.absent:
        add(entry.modality, entry.body_part or primary, performed=False)

    if not scenario.performed and not scenario.absent:
        for position, part in enumerate(parts):
            # The first region is always studied — a claim that reached a
            # medical-legal evaluation without imaging its main complaint is
            # rarer than the realism gained by pretending otherwise.
            if position == 0 or rng.random() < 0.6:
                add(rng.choice(_DERIVABLE_MODALITIES), part, performed=True)
            else:
                add(rng.choice(_DERIVABLE_MODALITIES), part, performed=False)

    return tuple(facts)


def _derive_surgery(seed: CaseSeed, timeline: Any) -> SurgeryFact:
    """Surgery status, absorbing the substrate's 35% coin without moving it.

    ``lifecycle_bridge`` drew ``rng.random() < 0.35`` off the ``clinical``
    stream to set ``has_surgery``. That draw still happens there and still gates
    the same document rules; this reads the *same* stream at the same point so
    the two agree, rather than flipping a second coin that could disagree with
    the document set already planned.
    """
    parts = _body_parts(seed)
    part = parts[0] if parts else "lumbar_spine"

    if seed.scenario.surgery == "performed":
        performed = True
    elif seed.scenario.surgery == "none":
        performed = False
    else:
        # Parity path. Reproduces ``lifecycle_bridge.seed_to_case_parameters``
        # term for term — including its psych rule, where naming
        # ``lc3208_3_psych`` counts as a psychiatric component — and reads the
        # same ``clinical`` stream at the same position (``seed.rng`` builds a
        # fresh Random per call, and that draw is its first). Any divergence
        # here would put a surgery in the ledger that the planned document set
        # does not contain, or the reverse.
        psych = any(part == "psyche" for part in parts) or (
            "lc3208_3_psych" in seed.lifecycle.doctrine_hooks
        )
        performed = (
            seed.injury.type != "death" and not psych and seed.rng("clinical").random() < 0.35
        )

    if not performed:
        return SurgeryFact(status="none")

    code, description = SURGERY_CPT_CODES.get(part, _DEFAULT_CPT)
    onset = getattr(timeline, "injury_date", None) or seed.injury.onset_date
    return SurgeryFact(
        status="performed",
        body_part=part,
        cpt_code=code,
        cpt_description=description,
        date=onset + timedelta(days=210),
    )


def _derive_providers(seed: CaseSeed, cast: Any) -> tuple[ProviderFact, ...]:
    """Two to four providers, scaled by how far the case went.

    Mirrors the substrate's ``prior_providers`` shape rather than inventing a
    new one, so a records packet attributed to provider *n* names someone the
    rest of the file already knows about.
    """
    rng = _rng(seed, "providers")
    stage = seed.lifecycle.target_stage
    reach = {
        "intake": 1,
        "active_treatment": 2,
        "discovery": 3,
        "medical_legal": 3,
        "pre_trial": 4,
        "resolved": 4,
        "post_recon": 4,
    }.get(stage, 3)

    treating = getattr(cast, "treating_physician", None) or "Treating Physician"
    facility = getattr(cast, "treating_facility", None) or "Valley Orthopedic Medical Group"
    providers = [
        ProviderFact(name=str(treating), specialty="Orthopedic Surgery", facility=str(facility))
    ]

    pool = [
        ("Physical Medicine & Rehabilitation", "Bayside Rehabilitation Associates"),
        ("Radiology", "Coastal Imaging Center"),
        ("Pain Management", "Northgate Pain Institute"),
        ("Neurology", "Harborview Neurology Group"),
    ]
    rng.shuffle(pool)
    for specialty, clinic in pool[: max(0, reach - 1)]:
        providers.append(
            ProviderFact(
                name=f"{specialty.split()[0]} Service, {clinic}",
                specialty=specialty,
                facility=clinic,
            )
        )
    return tuple(providers)


def _derive_visits(seed: CaseSeed, timeline: Any, surgery: SurgeryFact) -> tuple[VisitFact, ...]:
    """A dated visit series consistent with the timeline it hangs off."""
    onset = getattr(timeline, "injury_date", None) or seed.injury.onset_date
    horizon = getattr(timeline, "resolution_date", None) or getattr(
        timeline, "application_filed_date", None
    )
    visits: list[VisitFact] = [VisitFact(date=onset + timedelta(days=3), kind="initial")]

    step = 45
    for position in range(1, 6):
        moment = onset + timedelta(days=3 + step * position)
        if horizon is not None and moment > horizon:
            break
        kind: Literal["initial", "follow_up", "post_operative", "final"] = "follow_up"
        if surgery.performed and surgery.date is not None and moment > surgery.date:
            kind = "post_operative"
        visits.append(VisitFact(date=moment, kind=kind))
    return tuple(visits)


def derive_case_facts(seed: CaseSeed, timeline: Any, cast: Any = None) -> CaseFacts:
    """Decide, once, what clinically happened in this case.

    Args:
        seed: the case seed. ``scenario:`` is authoritative wherever it speaks.
        timeline: the built :class:`CaseTimeline`, so dates hang off the same
            spine the documents do.
        cast: the case cast, when one exists — supplies the treating physician
            so the provider list names people the file already knows.

    Returns:
        A frozen :class:`CaseFacts`. Derivation is pure: same seed, same facts.
    """
    diagnostics = _derive_diagnostics(seed, timeline)
    surgery = _derive_surgery(seed, timeline)
    providers = _derive_providers(seed, cast)
    visits = _derive_visits(seed, timeline, surgery)

    rng = _rng(seed, "rating")
    mmi = getattr(timeline, "resolution_date", None)
    onset = getattr(timeline, "injury_date", None) or seed.injury.onset_date
    if mmi is None:
        mmi = onset + timedelta(days=300)
    wpi = rng.randint(3, 24) if seed.lifecycle.eval_type != "none" else None
    pd = min(100, int(wpi * 1.4)) if wpi is not None else None

    facts = CaseFacts(
        diagnostics=diagnostics,
        surgery=surgery,
        providers=providers,
        visits=visits,
        mmi_date=mmi,
        wpi=wpi,
        pd=pd,
    )
    log.debug(
        "case_facts.derived",
        case_id=seed.case_id,
        performed=len(facts.performed_diagnostics),
        absent=len(facts.absent_diagnostics),
        surgery=facts.surgery.status,
        providers=len(facts.providers),
    )
    return facts


def facts_manifest_block(facts: CaseFacts) -> dict[str, Any]:
    """The ``caseFacts`` object a manifest publishes.

    Published so the ledger is auditable from the output alone: a reader with
    the manifest and the documents can check every coherence claim this package
    makes without rerunning the generator.
    """
    return {
        "diagnostics": [
            {
                "modality": fact.modality,
                "display": fact.display,
                "bodyPart": fact.body_part,
                "date": fact.date.isoformat() if fact.date else None,
                "performed": fact.performed,
            }
            for fact in facts.diagnostics
        ],
        "surgery": {
            "status": facts.surgery.status,
            "bodyPart": facts.surgery.body_part,
            "cptCode": facts.surgery.cpt_code,
            "cptDescription": facts.surgery.cpt_description,
            "date": facts.surgery.date.isoformat() if facts.surgery.date else None,
        },
        "providers": [
            {"name": p.name, "specialty": p.specialty, "facility": p.facility}
            for p in facts.providers
        ],
        "visits": [{"date": v.date.isoformat(), "kind": v.kind} for v in facts.visits],
        "mmiDate": facts.mmi_date.isoformat() if facts.mmi_date else None,
        "wpi": facts.wpi,
        "pd": facts.pd,
    }


__all__ = [
    "MODALITIES",
    "MODALITY_DISPLAY",
    "SURGERY_CPT_CODES",
    "CaseFacts",
    "DiagnosticFact",
    "Modality",
    "ProviderFact",
    "SurgeryFact",
    "VisitFact",
    "derive_case_facts",
    "facts_manifest_block",
]
